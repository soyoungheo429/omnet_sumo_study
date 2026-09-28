# -*- coding: utf-8 -*-
"""
algo2_bruteforce_grid/select_candidates.py
================================================================
전체 영역을 격자(grid_size 간격)로 나눠 각 칸의 중심점을 후보로 삼는
브루트포스 탐색용 후보 생성. 원본은 algo2_grid_150n_corrected.py.
격자 해상도가 성능에 미치는 한계는 이미 확인됨(150m 격자가 실제 명당을
놓칠 수 있음) - 보고서 참고.
================================================================
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from rsu_lib import coord_transform  # noqa: E402

WIDTH = 2606.46
HEIGHT = 3009.73


def select_candidates(grid_size: float = 150.0, margin: float = None) -> list:
    """반환: [(id, Sim_X, Sim_Y), ...] - 격자 전체, 이미 좌표 보정 적용됨."""
    if margin is None:
        margin = coord_transform.DEFAULT_MARGIN

    num_x = int(WIDTH // grid_size)
    num_y = int(HEIGHT // grid_size)

    candidates = []
    cand_id = 1
    for i in range(num_x):
        for j in range(num_y):
            rel_x = i * grid_size + grid_size / 2
            rel_y = j * grid_size + grid_size / 2
            sim_x, sim_y = coord_transform.traci2omnet(
                rel_x + coord_transform.TOPLEFT_X,
                rel_y + coord_transform.TOPLEFT_Y,
                margin,
            )
            candidates.append((f"Grid_{cand_id}", sim_x, sim_y))
            cand_id += 1
    return candidates
