# -*- coding: utf-8 -*-
"""
rsu_lib/bruteforce.py — 후보 C곳 중 K곳의 모든 조합을 다 따져 커버 최대인 조합을 찾는 전수 조사 (brute force)
  - 가지치기(branch-and-bound): "지금까지 고른 것 + 남은 자리에 단독으로 가장 많이 새로 덮는 후보들"의 합이
    지금까지 찾은 최고값 이하이면 그 가지는 더 볼 필요 없음 (커버는 겹치면 손해라 이 합이 상한)
  - 가지치기는 답을 바꾸지 않음 → 결과는 모든 조합을 본 것과 같음 (정확한 최적)
  - time_limit 안에 못 끝나면 Finished=False (그때까지의 최고값만 반환)
"""
import time

import numpy as np


def brute_force_max_cover(M, K, incumbent=None, time_limit=600):
    """M: (C, N) bool 커버리지 행렬. 반환: (선택 idx, 커버 %, 끝까지 봤는지, 본 노드 수, 초)"""
    t0 = time.time()
    C, N = M.shape
    best = {"val": -1, "sel": None}
    if incumbent is not None:
        best["val"] = int(M[list(incumbent)].any(0).sum())
        best["sel"] = list(incumbent)
    nodes = [0]
    finished = [True]

    def dfs(start, sel, covered, ncov):
        nodes[0] += 1
        if time.time() - t0 > time_limit:
            finished[0] = False
            return
        r = K - len(sel)
        if r == 0:
            if ncov > best["val"]:
                best["val"], best["sel"] = ncov, list(sel)
            return
        if C - start < r:
            return
        gains = (M[start:] & ~covered).sum(1)
        top = np.sort(gains)[::-1][:r].sum()
        if ncov + top <= best["val"]:
            return
        order = np.argsort(-gains)            # 많이 새로 덮는 후보부터 → 좋은 답을 빨리 찾아 가지치기 강화
        for j in order:
            i = start + int(j)
            if gains[j] == 0 and best["val"] >= ncov:
                break
            # 같은 조합을 두 번 보지 않도록 i보다 큰 번호만 다음 단계 후보로 (start = i+1)
            dfs(i + 1, sel + [i], covered | M[i], ncov + int(gains[j]))
            if not finished[0]:
                return

    dfs(0, [], np.zeros(N, bool), 0)
    return best["sel"], best["val"] / N * 100, finished[0], nodes[0], time.time() - t0
