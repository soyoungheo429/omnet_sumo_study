# -*- coding: utf-8 -*-
"""
algo1_intersection/select_candidates.py
================================================================
교차로 차수(degree)+밀집도(density) 기반 후보 선정. 원본은
step3_extract_candidates.py + step5_extract_candidates2.py.
좌표(=net.xml raw x,y)는 유클리드 거리 기반 필터링이라 좌표 버그와
무관했음(이미 검증됨) - 이 로직 자체는 그대로 두고, 최종 반환 시에만
traci2omnet() 보정을 적용한다.
================================================================
"""

import sys
import os
import math
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from rsu_lib import coord_transform  # noqa: E402


def _distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def select_candidates(
    net_xml_path: str,
    min_dist: float = 150.0,
    min_degree: int = 3,
    margin: float = None,
) -> list:
    """반환: [(Sim_X, Sim_Y), ...] - 차수 내림차순, 밀집도 순으로 정렬되고
    최소거리 필터까지 적용된, 이미 좌표 보정된 리스트."""
    if margin is None:
        margin = coord_transform.DEFAULT_MARGIN

    tree = ET.parse(net_xml_path)
    root = tree.getroot()

    candidates = []
    for junction in root.findall("junction"):
        if junction.get("type") not in (
            "priority",
            "traffic_light",
            "right_before_left",
        ):
            continue
        x, y = float(junction.get("x")), float(junction.get("y"))
        degree = len(junction.get("incLanes", "").split())
        if degree >= min_degree:
            candidates.append(
                {"id": junction.get("id"), "pos": (x, y), "degree": degree}
            )

    for c in candidates:
        c["density"] = sum(
            1
            for o in candidates
            if c is not o and _distance(c["pos"], o["pos"]) < min_dist
        )

    candidates.sort(key=lambda c: (c["degree"], c["density"]), reverse=True)

    selected = []
    for c in candidates:
        if not any(_distance(c["pos"], s["pos"]) < min_dist for s in selected):
            selected.append(c)

    return [
        coord_transform.traci2omnet(c["pos"][0], c["pos"][1], margin) for c in selected
    ]
