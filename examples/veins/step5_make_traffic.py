#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_make_traffic.py   (SUMO 없이 순수 파이썬, 몇 초)
================================================================
교수님 코멘트: 같은 지도에서 이동 패턴 3종 → 평균·표준편차
  P1 기존     : 지금까지 쓴 erlangen.rou.xml 그대로 (랜덤 출발·도착, 47대)
  P2 도심 집중: 출발·목적지를 도심(도로 밀도 최고 지점)에 몰리게 뽑음 (가우시안 가중치, σ=350m)
  P3 간선 통과: 지도 가장자리 → 반대쪽 가장자리로 지나가는 차량, 빠른 도로(간선) 선호
공통: 차량 47대, 출발 0~0.92초(기존과 동일), 경로는 목적지를 이어 붙여 ≥6km
      (200초 동안 지도 밖으로 나가지 않게 — 기존 step2 '무한 경로'와 같은 취지)
출력: erlangen_P{1,2,3}.rou.xml(P1은 기존 파일 참조), erlangen_P*.sumo.cfg, erlangen_P*.launchd.xml
      experiment_results/step5/traffic_patterns_summary.csv
실행: python3 step5_make_traffic.py
================================================================
"""
import heapq
import math
import os
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
NET = "erlangen.net.xml"
N_VEH, DT_DEPART, MIN_ROUTE_M = 47, 0.02, 6000.0
OUT = os.path.join("experiment_results", "step5")
OFFSET_X, OFFSET_Y, HEIGHT, MARGIN = 644465.09, 5491786.25, 3009.73, 25.0


def to_sim(x, y):
    return x - OFFSET_X + MARGIN, HEIGHT - (y - OFFSET_Y) + MARGIN


def lane_ok(l):
    allow, dis = l.get("allow"), l.get("disallow", "")
    if allow is not None:
        return "passenger" in allow.split()
    return "passenger" not in dis.split() and dis != "all"


def load_net():
    root = ET.parse(NET).getroot()
    E = {}
    for e in root.findall("edge"):
        if e.get("function") == "internal":
            continue
        lanes = e.findall("lane")
        ok = {int(l.get("index")) for l in lanes if lane_ok(l)}
        if not ok:
            continue
        l0 = lanes[0]
        sh = np.array([tuple(map(float, s.split(","))) for s in l0.get("shape").split()])
        mx, my = to_sim(*sh[len(sh) // 2])
        E[e.get("id")] = dict(len=float(l0.get("length")), speed=max(float(l0.get("speed")), 1.0),
                              x=mx, y=my, lanes=ok, out=set(), frm=e.get("from"), to=e.get("to"))
    for c in root.findall("connection"):
        f, t = c.get("from"), c.get("to")
        if f in E and t in E and int(c.get("fromLane")) in E[f]["lanes"] and int(c.get("toLane")) in E[t]["lanes"]:
            E[f]["out"].add(t)
    # 강하게 연결된 가장 큰 덩어리만 사용 (막다른 길에 갇히지 않게)
    ids = list(E)
    s0 = ids[int(np.argmax([len(E[i]["out"]) for i in ids]))]
    fwd = _reach(E, s0)
    rev = {i: set() for i in E}
    for i in E:
        for j in E[i]["out"]:
            rev[j].add(i)
    keep = fwd & _reach_rev(rev, s0)
    E = {i: v for i, v in E.items() if i in keep}
    for v in E.values():
        v["out"] &= keep
    return E


def _reach(E, s):
    seen, st = {s}, [s]
    while st:
        for j in E[st.pop()]["out"]:
            if j not in seen:
                seen.add(j); st.append(j)
    return seen


def _reach_rev(rev, s):
    seen, st = {s}, [s]
    while st:
        for j in rev[st.pop()]:
            if j not in seen:
                seen.add(j); st.append(j)
    return seen


def dijkstra(E, s, t, cost):
    dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == t:
            break
        if d > dist[u]:
            continue
        for v in E[u]["out"]:
            nd = d + cost[v]
            if nd < dist.get(v, 1e18):
                dist[v], prev[v] = nd, u
                heapq.heappush(pq, (nd, v))
    if t not in dist:
        return None
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]


def downtown(E):
    """도로(엣지 중점) 밀도가 가장 높은 지점 = 도심"""
    P = np.array([[v["x"], v["y"]] for v in E.values()])
    best, bc = None, -1
    for gx in np.arange(P[:, 0].min(), P[:, 0].max(), 50):
        for gy in np.arange(P[:, 1].min(), P[:, 1].max(), 50):
            c = int((np.hypot(P[:, 0] - gx, P[:, 1] - gy) < 400).sum())
            if c > bc:
                best, bc = (gx, gy), c
    return best


def make_pattern(E, name, rng):
    ids = list(E)
    X = np.array([E[i]["x"] for i in ids]); Y = np.array([E[i]["y"] for i in ids])
    L = np.array([E[i]["len"] for i in ids])
    if name == "P2":
        cx, cy = downtown(E)
        w = L * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * 350.0 ** 2))
        cost = {i: E[i]["len"] / E[i]["speed"] for i in ids}
        w_start = w
    else:  # P3: 가장자리 300m 띠의 엣지끼리, 빠른 도로 선호(시간 × 13.9/속도)
        x0, x1, y0, y1 = X.min(), X.max(), Y.min(), Y.max()
        edge_d = np.minimum.reduce([X - x0, x1 - X, Y - y0, y1 - Y])
        w = L * (edge_d < 300)
        cost = {i: E[i]["len"] / E[i]["speed"] * (13.9 / E[i]["speed"]) for i in ids}
        w_start = w
    p = w / w.sum(); ps = w_start / w_start.sum()
    routes = []
    for v in range(N_VEH):
        cur = ids[rng.choice(len(ids), p=ps)]
        route, total = [cur], E[cur]["len"]
        tries = 0
        while total < MIN_ROUTE_M and tries < 200:
            tries += 1
            dst = ids[rng.choice(len(ids), p=p)]
            dd = math.hypot(E[dst]["x"] - E[cur]["x"], E[dst]["y"] - E[cur]["y"])
            if dst == cur or dd < (1200 if name == "P3" else 250):
                continue
            path = dijkstra(E, cur, dst, cost)
            if not path or len(path) < 2:
                continue
            route += path[1:]
            total += sum(E[e]["len"] for e in path[1:])
            cur = dst
        routes.append(route)
    return routes


def write_routes(path, routes):
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!-- step5_make_traffic.py -->\n<routes>\n')
        for i, r in enumerate(routes):
            f.write(f'    <vehicle id="{i}" depart="{i * DT_DEPART:.2f}" departLane="best" departPos="random" departSpeed="max">\n'
                    f'        <route edges="{" ".join(r)}"/>\n    </vehicle>\n')
        f.write("</routes>\n")


def read_routes(path):
    return [v.find("route").get("edges").split() for v in ET.parse(path).getroot().iter("vehicle")]


CFG = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="erlangen.net.xml"/>
        <route-files value="{rou}"/>
        <additional-files value="erlangen.poly.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="200"/>
        <step-length value="0.05"/>
    </time>
    <report>
        <xml-validation value="never"/>
        <xml-validation.net value="never"/>
        <no-step-log value="true"/>
    </report>
</configuration>
"""
LAUNCHD = """<?xml version="1.0"?>
<!-- step5 traffic pattern {p} -->
<launch>
    <copy file="erlangen.net.xml" />
    <copy file="{rou}" />
    <copy file="erlangen.poly.xml" />
    <copy file="erlangen_{p}.sumo.cfg" type="config" />
</launch>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    E = load_net()
    print(f"도로 엣지 {len(E)}개 (승용차 통행 + 서로 연결된 덩어리)")
    cx, cy = downtown(E)
    print(f"도심(도로 밀도 최고) = ({cx:.0f}, {cy:.0f})  [시뮬 좌표]")
    rows = []
    for p, seed in (("P1", None), ("P2", 2), ("P3", 3)):
        if p == "P1":
            rou, routes = "erlangen.rou.xml", read_routes("erlangen.rou.xml")
        else:
            rou = f"erlangen_{p}.rou.xml"
            routes = make_pattern(E, p, np.random.default_rng(seed))
            write_routes(rou, routes)
        with open(f"erlangen_{p}.sumo.cfg", "w", encoding="utf-8") as f:
            f.write(CFG.format(rou=rou))
        with open(f"erlangen_{p}.launchd.xml", "w", encoding="utf-8") as f:
            f.write(LAUNCHD.format(p=p, rou=rou))
        # 요약: 경로 길이, 도심 600m 안 비율, 간선(>=60km/h) 비율 — 첫 2km(≈200초 주행분) 기준
        Ls, cen, art = [], [], []
        for r in routes:
            acc, c, a, tot = 0.0, 0.0, 0.0, 0.0
            for e in r:
                if e not in E:
                    continue
                l = E[e]["len"]
                if acc > 2000:
                    break
                acc += l; tot += l
                c += l * (math.hypot(E[e]["x"] - cx, E[e]["y"] - cy) < 600)
                a += l * (E[e]["speed"] >= 16.0)
            Ls.append(sum(E[e]["len"] for e in r if e in E)); cen.append(c / max(tot, 1)); art.append(a / max(tot, 1))
        rows.append(dict(Pattern=p, Route_file=rou, Vehicles=len(routes), Route_km_mean=round(np.mean(Ls) / 1000, 2),
                         Downtown600m_share=round(100 * np.mean(cen), 1), Arterial_share=round(100 * np.mean(art), 1)))
    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(OUT, "traffic_patterns_summary.csv"), index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))
    print("다음: VM에서 python3 step5_snapshots.py  (SUMO로 차량 위치 스냅샷 추출)")


if __name__ == "__main__":
    main()
