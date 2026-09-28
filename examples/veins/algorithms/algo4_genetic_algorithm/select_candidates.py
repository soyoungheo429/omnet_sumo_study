# -*- coding: utf-8 -*-
"""
algo4_genetic_algorithm/select_candidates.py
================================================================
주의: GA도 SA와 마찬가지로 세대마다 시뮬레이션 PDR 피드백이 필요한
탐색 알고리즘이라, 순수 select_candidates(...) 형태로 완전히 분리되지
않는다. 여기서는 "교차/돌연변이" 순수 연산만 분리해서 노출.

전체 실행(초기 인구 생성 + 시뮬레이션 포함)은
../../algo4_GA_corrected.py 를 그대로 쓴다 (이미 좌표 보정 적용됨).
================================================================
"""

import math
import random

WIDTH = 2606.46
HEIGHT = 3009.73


def weighted_crossover(p1: dict, p2: dict) -> dict:
    total_pdr = p1["pdr"] + p2["pdr"]
    w1, w2 = (
        (0.5, 0.5) if total_pdr <= 0 else (p1["pdr"] / total_pdr, p2["pdr"] / total_pdr)
    )
    child_x = p1["x"] * w1 + p2["x"] * w2
    child_y = p1["y"] * w1 + p2["y"] * w2
    if random.random() < 0.3:
        ext = random.uniform(1.1, 1.3)
        child_x = p2["x"] + (p1["x"] - p2["x"]) * ext
        child_y = p2["y"] + (p1["y"] - p2["y"]) * ext
    return {"x": child_x, "y": child_y, "pdr": -1.0}


def mutate(ind: dict, mutation_rate: float = 0.2) -> dict:
    if random.random() < mutation_rate:
        dist = random.uniform(50, 200)
        angle = random.uniform(0, 2 * math.pi)
        ind["x"] = max(0, min(WIDTH, ind["x"] + dist * math.cos(angle)))
        ind["y"] = max(0, min(HEIGHT, ind["y"] + dist * math.sin(angle)))
    return ind


# 전체 실행(시뮬레이션 포함)은 다음 파일 참고:
#   ../../algo4_GA_corrected.py  (좌표 보정 이미 적용된 버전)
