#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_snapshots.py   (VM, SUMO만 사용 — 패턴당 수십 초)
================================================================
패턴별 SUMO를 단독 실행 → 차량 위치를 10~200초, 2초 간격으로 기록 (기존 vehicle_snapshots_2s.csv와 같은 방식)
  P1 = 기존 vehicle_snapshots_2s.csv 그대로 복사 (step4와 같은 데이터)
출력: vehicle_snapshots_2s_<시나리오>.csv   (시나리오 = P1..P3 Erlangen / DA_P1..DA_P3 Darmstadt)
      experiment_results/step5/traffic_patterns_map[_<지도>].png   (패턴별 차량 위치 분포)
      experiment_results/step5/traffic_patterns_alive[_<지도>].csv (시간별 지도 위 차량 수 — 200초 내내 47대 유지되는지)
실행: python3 step5_snapshots.py                              (Erlangen)
      python3 step5_snapshots.py --patterns DA_P1,DA_P2,DA_P3  (Darmstadt)
================================================================
"""
import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib import scenario as SC  # noqa: E402
from rsu_lib import surrogate as SG  # noqa: E402

OUT = os.path.join("experiment_results", "step5")


def fcd_to_csv(xml, csv, start=10.0, end=200.0, interval=2.0):
    rows, alive, n, nxt = [], [], 0, start
    for ev, el in ET.iterparse(xml, events=("end",)):
        if el.tag != "timestep":
            continue
        t = float(el.get("time"))
        vs = el.findall("vehicle")
        if abs(t - round(t)) < 1e-6:
            alive.append((t, len(vs)))
        if start - 0.01 <= t <= end and t >= nxt - 0.01 and vs:
            n += 1
            rows += [dict(snapshot_no=n, time=t, vehicle_id=v.get("id"), x=float(v.get("x")), y=float(v.get("y"))) for v in vs]
            nxt += interval
        el.clear()
    pd.DataFrame(rows).to_csv(csv, index=False, encoding="utf-8-sig")
    return len(rows), n, alive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns", default="P1,P2,P3")
    ap.add_argument("--sumo", default="sumo")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    alive_all = {}
    pats = a.patterns.split(",")
    for p in pats:
        F = SC.files(p)
        csv = F["snap"]
        if p == "P1":
            shutil.copy("vehicle_snapshots_2s.csv", csv)
            print(f"{p}: 기존 vehicle_snapshots_2s.csv 복사")
            continue
        xml = os.path.join(OUT, f"_fcd_{p}.xml")
        cmd = [a.sumo, "-c", F["cfg"], "--fcd-output", xml, "--seed", "0", "--no-warnings", "true"]
        print(" ".join(cmd), flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(r.stderr[-1500:])
        tele = [l for l in (r.stdout + r.stderr).splitlines() if "eleport" in l]
        n, ns, alive = fcd_to_csv(xml, csv)
        alive_all[p] = dict(alive)
        print(f"{p}: 점 {n}개, 스냅샷 {ns}장, 지도 위 차량 수 min {min(c for _, c in alive)} / 끝 {alive[-1][1]}"
              f"  텔레포트 언급 {len(tele)}줄 → {csv}")
        os.remove(xml)
    mp = SC.files(pats[0])["map"]
    tag = "" if mp == "erlangen" else f"_{mp}"
    if alive_all:
        pd.DataFrame(alive_all).rename_axis("time").to_csv(os.path.join(OUT, f"traffic_patterns_alive{tag}.csv"))
    # 지도
    SC.use(pats[0])
    W, H = SC.size(SC.files(pats[0])["net"])
    ps = [p for p in pats if os.path.exists(SC.files(p)["snap"])]
    fig, axes = plt.subplots(1, len(ps), figsize=(5 * len(ps), 5.6), sharex=True, sharey=True)
    axes = [axes] if len(ps) == 1 else axes
    names = {"P1": "P1 random", "P2": "P2 downtown-concentrated", "P3": "P3 arterial through-traffic"}
    for ax, p in zip(axes, ps):
        d = pd.read_csv(SC.files(p)["snap"], encoding="utf-8-sig")
        sx, sy = SG.utm_to_sim(d.x.to_numpy(), d.y.to_numpy())
        ax.hexbin(sx, sy, gridsize=35, cmap="Blues", mincnt=1, extent=(0, W, 0, H))
        ax.set_title(f"{names[SC.files(p)['pattern']]}  (n={len(d)})", loc="left", fontsize=10)
        ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{mp.capitalize()}: vehicle position density for 3 traffic patterns (10–200 s, every 2 s)", x=0.01, ha="left")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, f"traffic_patterns_map{tag}.png"), dpi=150); plt.close()
    print(f"다음: python3 -u step5_placements.py --patterns {','.join(pats)}")


if __name__ == "__main__":
    main()
