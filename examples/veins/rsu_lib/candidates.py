# -*- coding: utf-8 -*-
"""
rsu_lib/candidates.py — RSU 후보지 풀 (모두 시뮬레이션 좌표)
  intersections(min_degree=3) : algo1과 같은 기준(진입 차선 3개 이상 교차로), 150m 필터는 하지 않음
  all_junctions()             : algo7과 같은 기준(dead_end/internal 제외 모든 교차로)
  road_points(step)           : 차선 중심선을 step(m) 간격으로 샘플링한 도로 위 점 (연속 탐색·GA 돌연변이용)
"""
import xml.etree.ElementTree as ET

import numpy as np

from rsu_lib.surrogate import utm_to_sim


def _junctions(net_xml):
    for j in ET.parse(net_xml).getroot().findall("junction"):
        yield j


def intersections(net_xml, min_degree=3):
    out = []
    for j in _junctions(net_xml):
        if j.get("type") not in ("priority", "traffic_light", "right_before_left"):
            continue
        if len(j.get("incLanes", "").split()) >= min_degree:
            out.append((j.get("id"),) + utm_to_sim(float(j.get("x")), float(j.get("y"))))
    return out


def all_junctions(net_xml):
    out = []
    for j in _junctions(net_xml):
        if j.get("type") in ("dead_end", "internal", "unregulated"):
            continue
        out.append((j.get("id"),) + utm_to_sim(float(j.get("x")), float(j.get("y"))))
    return out


def road_points(net_xml, step=25.0):
    pts = []
    for e in ET.parse(net_xml).getroot().findall("edge"):
        if e.get("function") == "internal":
            continue
        lane = e.find("lane")
        if lane is None:
            continue
        sh = np.array([tuple(map(float, s.split(","))) for s in lane.get("shape").split()])
        seg = np.diff(sh, axis=0)
        L = np.hypot(seg[:, 0], seg[:, 1])
        cum = np.r_[0, np.cumsum(L)]
        for d in np.arange(0, cum[-1] + 1e-9, step):
            i = min(np.searchsorted(cum, d, side="right") - 1, len(L) - 1)
            t = 0 if L[i] == 0 else (d - cum[i]) / L[i]
            x, y = sh[i] + t * seg[i]
            pts.append(utm_to_sim(x, y))
    pts = np.unique(np.round(np.array(pts), 0), axis=0)
    return pts
