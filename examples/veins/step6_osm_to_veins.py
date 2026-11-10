#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step6_osm_to_veins.py   (VM — OSM 다운로드 + SUMO netconvert/polyconvert, 몇 분)
================================================================
교수님 코멘트: 다른 지도에서도 같은 실험 → Darmstadt 도심 (Erlangen과 비슷한 약 2.6 × 3.0 km)
  1) OpenStreetMap에서 영역 다운로드 (Overpass API)                         → darmstadt.osm
  2) netconvert: 승용차 도로만, 좌표는 UTM 그대로(Erlangen과 같은 방식)       → darmstadt.net.xml
  3) polyconvert: 건물 외곽선 → type="building" 만 남김 (Veins 건물 감쇠: 벽 1번 9dB + 건물 안 0.4dB/m,
     config.xml 의 SimpleObstacleShadowing 이 type="building" 다각형을 그대로 씀)  → darmstadt.poly.xml
  4) 점검: 도로·교차로·건물 수를 Erlangen과 비교, 도로+건물 지도 그림
출력: darmstadt.osm / .net.xml / .poly.xml, experiment_results/step5/map_check_darmstadt.png, map_compare.csv
실행: python3 step6_osm_to_veins.py
      (VM에서 다운로드가 막히면: 브라우저로 아래 URL을 열어 darmstadt.osm 으로 저장 후 다시 실행)
다음: python3 step5_make_traffic.py --map darmstadt
================================================================
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
OUT = os.path.join("experiment_results", "step5")
# 남, 서, 북, 동  (Darmstadt 도심: Luisenplatz 중심, 약 2.6 km × 3.0 km)
BBOX = dict(darmstadt=(49.859, 8.633, 49.886, 8.669))
SERVERS = ["https://overpass-api.de/api/map?bbox={w},{s},{e},{n}",
           "https://overpass.kumi.systems/api/map?bbox={w},{s},{e},{n}"]
TYPEMAP = """<polygonTypes>
    <polygonType id="building" name="building" color="1,0,0" layer="-1"/>
</polygonTypes>
"""


def tool(name):
    if not os.environ.get("SUMO_HOME"):          # xsd를 인터넷에서 찾다 실패하는 것 방지
        for cand in ("/home/veins/src/sumo", "/usr/share/sumo", "/usr/local/share/sumo"):
            if os.path.isdir(os.path.join(cand, "data", "xsd")):
                os.environ["SUMO_HOME"] = cand
                break
    for d in [os.path.join(os.environ.get("SUMO_HOME", ""), "bin"), ""]:
        p = shutil.which(os.path.join(d, name) if d else name)
        if p:
            return p
    sys.exit(f"{name} 를 찾지 못함 (SUMO_HOME 또는 PATH 확인)")


def run(cmd):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit((r.stdout + r.stderr)[-2000:])
    return r


def download(name, osm):
    if os.path.exists(osm) and os.path.getsize(osm) > 10000:
        print(f"{osm} 이미 있음 ({os.path.getsize(osm) / 1e6:.1f} MB) → 다운로드 생략")
        return
    s, w, n, e = BBOX[name]
    for url in SERVERS:
        url = url.format(s=s, w=w, n=n, e=e)
        print("다운로드:", url, flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rsu-placement-study/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(osm, "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(osm) > 10000:
                print(f"  → {osm} {os.path.getsize(osm) / 1e6:.1f} MB")
                return
        except Exception as ex:  # 다음 서버 시도
            print("  실패:", ex)
    sys.exit("OSM 다운로드 실패 → 위 URL을 브라우저로 열어 저장한 뒤 다시 실행하세요.")


def filter_buildings(src, dst, net_xml):
    from rsu_lib.scenario import boundary
    x0, y0, x1, y1 = boundary(net_xml)
    root = ET.parse(src).getroot()
    keep, drop = [], 0
    for p in root.findall("poly"):
        if p.get("type") != "building":
            drop += 1
            continue
        pts = np.array([tuple(map(float, q.split(","))) for q in p.get("shape").split()])
        if len(pts) < 3 or pts[:, 0].max() < x0 - 50 or pts[:, 0].min() > x1 + 50 or pts[:, 1].max() < y0 - 50 or pts[:, 1].min() > y1 + 50:
            drop += 1
            continue
        keep.append(p)
    with open(dst, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!-- step6_osm_to_veins.py: OSM 건물만 (c) OpenStreetMap contributors, ODbL -->\n<additional>\n')
        for p in keep:
            f.write(f'    <poly id="{p.get("id")}" type="building" color="1,0,0" fill="1" layer="-1.00" shape="{p.get("shape")}"/>\n')
        f.write("</additional>\n")
    return len(keep), drop


def stats(name):
    from rsu_lib import candidates as CA, scenario as SC, surrogate as SG
    SG.set_map(f"{name}.net.xml")
    x0, y0, x1, y1 = SC.boundary(f"{name}.net.xml")
    root = ET.parse(f"{name}.net.xml").getroot()
    edges = [e for e in root.findall("edge") if e.get("function") != "internal"]
    L = sum(float(e.find("lane").get("length")) for e in edges if e.find("lane") is not None)
    bld = SG.load_buildings(f"{name}.poly.xml")
    return dict(Map=name, Width_km=round((x1 - x0) / 1000, 2), Height_km=round((y1 - y0) / 1000, 2),
                Edges=len(edges), Road_km=round(L / 1000, 1), Intersections_A=len(CA.intersections(f"{name}.net.xml")),
                Junctions_B=len(CA.all_junctions(f"{name}.net.xml")), RoadPoints_R=len(CA.road_points(f"{name}.net.xml", 25)),
                Buildings=len(bld))


def draw(name):
    from rsu_lib import scenario as SC, surrogate as SG
    SG.set_map(f"{name}.net.xml")
    W, H = SC.size(f"{name}.net.xml")
    fig, ax = plt.subplots(figsize=(6, 6.8))
    for P in SG.load_buildings(f"{name}.poly.xml"):
        ax.fill(P[:, 0], P[:, 1], color="#e4a0a0", lw=0)
    for e in ET.parse(f"{name}.net.xml").getroot().findall("edge"):
        if e.get("function") == "internal" or e.find("lane") is None:
            continue
        sh = np.array([tuple(map(float, s.split(","))) for s in e.find("lane").get("shape").split()])
        sx, sy = SG.utm_to_sim(sh[:, 0], sh[:, 1])
        ax.plot(sx, sy, color="#52514e", lw=0.6)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{name.capitalize()}: roads (grey) + buildings (red, used for obstacle shadowing)", loc="left", fontsize=9)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, f"map_check_{name}.png"), dpi=150); plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="darmstadt", choices=list(BBOX))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    name = a.map
    osm, net, poly = f"{name}.osm", f"{name}.net.xml", f"{name}.poly.xml"
    download(name, osm)
    s, w, n, e = BBOX[name]
    run([tool("netconvert"), "--osm-files", osm, "-o", net,
         "--keep-edges.in-geo-boundary", f"{w},{s},{e},{n}",  # 다운로드 영역 밖으로 뻗은 도로는 자름 (Erlangen과 크기 맞춤)
         "--offset.disable-normalization", "true",          # Erlangen처럼 UTM 좌표 그대로 (convBoundary = UTM)
         "--keep-edges.by-vclass", "passenger", "--remove-edges.isolated", "true",
         "--geometry.remove", "true", "--roundabouts.guess", "true", "--ramps.guess", "true",
         "--junctions.join", "true", "--tls.guess-signals", "true", "--tls.discard-simple", "true", "--tls.join", "true",
         "--no-warnings", "true"])
    with open(f"_{name}.typ.xml", "w", encoding="utf-8") as f:
        f.write(TYPEMAP)
    run([tool("polyconvert"), "--osm-files", osm, "--net-file", net, "--type-file", f"_{name}.typ.xml",
         "-o", f"_{name}.poly.raw.xml", "--no-warnings", "true"])
    k, d = filter_buildings(f"_{name}.poly.raw.xml", poly, net)
    os.remove(f"_{name}.poly.raw.xml"); os.remove(f"_{name}.typ.xml")
    print(f"건물 {k}개 남김 (그 외 {d}개 제외) → {poly}")
    rows = [stats(name)]
    if os.path.exists("erlangen.net.xml"):
        rows.insert(0, stats("erlangen"))
    T = pd.DataFrame(rows)
    T.to_csv(os.path.join(OUT, "map_compare.csv"), index=False, encoding="utf-8-sig")
    print(T.to_string(index=False))
    draw(name)
    print(f"그림: {OUT}/map_check_{name}.png\n다음: python3 step5_make_traffic.py --map {name}")


if __name__ == "__main__":
    main()
