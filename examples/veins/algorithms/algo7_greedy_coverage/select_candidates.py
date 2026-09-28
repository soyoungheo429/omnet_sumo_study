# -*- coding: utf-8 -*-
"""
algo7_greedy_coverage/select_candidates.py
================================================================
Greedy Max Coverage: 차량 스냅샷을 최대한 많이 덮는 K개 후보를 순차적으로
선택 (submodular, (1-1/e) 근사 보장). 원본 로직은
algo7_rsu_max_coverage.py에 있고, 여기서는 "순수 선택 로직"만 재노출.
좌표 보정은 select_candidates()가 rsu_lib.coord_transform으로 직접 적용해서
반환하므로, 호출부는 바로 sim_runner에 넘기면 된다.
================================================================
"""

import sys
import os
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from rsu_lib import coord_transform  # noqa: E402


def greedy_max_coverage(
    points: np.ndarray, candidates: np.ndarray, radius: float, k: int
):
    """points/candidates: 이미 raw offset-only 좌표(net.xml 기준, 보정 전).
    반환: 선택된 후보들의 (raw_x, raw_y) 인덱스/좌표."""
    tree = cKDTree(points)
    coverage_sets = [set(lst) for lst in tree.query_ball_point(candidates, radius)]

    covered = set()
    selected = []
    remaining = set(range(len(candidates)))

    for _ in range(k):
        best_idx, best_gain = -1, -1
        for i in remaining:
            gain = len(coverage_sets[i] - covered)
            if gain > best_gain:
                best_gain, best_idx = gain, i
        if best_gain <= 0:
            break
        selected.append(best_idx)
        covered |= coverage_sets[best_idx]
        remaining.remove(best_idx)

    return selected


def select_candidates(
    points_raw: np.ndarray,
    candidates_raw: np.ndarray,
    k: int,
    radius: float = 150.0,
    margin: float = None,
) -> list:
    """반환: [(Sim_X, Sim_Y), ...] - 이미 traci2omnet() 보정 적용된, ini에
    바로 쓸 수 있는 좌표 리스트."""
    if margin is None:
        margin = coord_transform.DEFAULT_MARGIN
    idx = greedy_max_coverage(points_raw, candidates_raw, radius, k)
    return [
        coord_transform.traci2omnet(candidates_raw[i][0], candidates_raw[i][1], margin)
        for i in idx
    ]
