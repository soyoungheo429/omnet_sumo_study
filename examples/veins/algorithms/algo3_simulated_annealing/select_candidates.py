# -*- coding: utf-8 -*-
"""
algo3_simulated_annealing/select_candidates.py
================================================================
주의: SA는 "후보 목록을 한 번에 뽑는" 알고리즘이 아니라, 매 스텝마다
직전 PDR 결과를 보고 다음 위치를 정하는 탐색(search) 알고리즘이라서,
다른 algo들처럼 순수 select_candidates(...) -> [좌표들] 형태로 분리가
안 된다 (시뮬레이션 실행과 알고리즘 로직이 반복적으로 맞물려 있음).

그래서 여기서는 "탐색 로직"만 뽑아서 노출하고, 실제 실행은
../../algo3_SA_corrected.py 를 그대로 쓴다 (이미 좌표 보정 적용됨).
================================================================
"""

import math
import random

WIDTH = 2606.46
HEIGHT = 3009.73


def propose_neighbor(curr_x, curr_y, step_size=150.0):
    """SA의 "다음 후보 위치 제안" 로직만 분리."""
    next_x = max(0, min(WIDTH, curr_x + random.uniform(-step_size, step_size)))
    next_y = max(0, min(HEIGHT, curr_y + random.uniform(-step_size, step_size)))
    return next_x, next_y


def accept_probability(curr_pdr, next_pdr, temp):
    delta = next_pdr - curr_pdr
    if delta > 0:
        return 1.0
    return math.exp(delta / temp) if temp > 0 else 0.0


# 전체 실행(시뮬레이션 포함)은 다음 파일 참고:
#   ../../algo3_SA_corrected.py  (좌표 보정 이미 적용된 버전)
