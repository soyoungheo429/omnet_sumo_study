# -*- coding: utf-8 -*-
"""
rsu_lib/lattice_ga.py — 연속 그룹 GA v3 (시뮬레이션 없음, 커버 지도 미리 계산)
================================================================
CoverLattice : 도로 중심선에서 buffer(30m) 안의 모든 위치를 step(5m) 간격으로 나눈 칸마다
               "여기 RSU를 두면 어느 차량 위치가 덮이나"를 근사 모델로 한 번만 계산해 저장 (비트 압축)
               → GA는 연속 좌표를 그대로 쓰고, 평가할 때 가장 가까운 칸 값을 찾아 씀 (평가 ≈ 0초)
LatticeGA    : 개체 = K개 연속 좌표 그룹
               선택   토너먼트(3), 엘리트 보존
               교차   두 부모의 RSU를 거리 기준으로 짝지음(헝가리안) → 짝마다 적합도 높은 부모 쪽 확률로 통째로 가져옴
               돌연변이 RSU마다 확률 max(1/K, 0.2)로 가우시안 이동, 폭 σ = 150m → 5m (세대가 갈수록 줄어듦)
               초기화 차량이 다니는 위치에서 K개
               (지난주 v2와 같은 연산, 평가만 미리 계산한 커버 지도로 바꾸고 예산을 키움)
================================================================
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from rsu_lib import candidates as CA
from rsu_lib.scenario import size

_S = None  # 병렬 계산용 (fork로 자식에 전달)


def _work(chunk):
    out = np.zeros((len(chunk), (len(_S.pts) + 7) // 8), np.uint8)
    for i, p in enumerate(chunk):
        out[i] = np.packbits(_S.rx_dbm(p, cache=False) >= _S.thresh)
    return out


class CoverLattice:
    def __init__(self, S, net_xml, step=5.0, buffer=30.0, cache=None, workers=None, log=None):
        log = log or (lambda m: print(m, flush=True))
        self.S, self.step, self.buffer = S, step, buffer
        n_pts = len(S.pts)
        if cache and os.path.exists(cache):
            z = np.load(cache)
            self.coords, self.packed, self.prep_s = z["coords"], z["packed"], float(z["prep_s"])
            log(f"  커버 지도: 캐시 사용 ({len(self.coords)}칸, 만들 때 {self.prep_s:.0f}s)")
        else:
            t0 = time.time()
            R = CA.road_points(net_xml, step)
            W, H = size(net_xml)
            gx, gy = np.meshgrid(np.arange(0, W, step), np.arange(0, H, step))
            G = np.c_[gx.ravel(), gy.ravel()]
            d, _ = cKDTree(R).query(G)
            self.coords = G[d <= buffer]
            log(f"  커버 지도: 도로 ±{buffer:.0f}m, {step:.0f}m 간격 {len(self.coords)}칸 계산 중...")
            global _S
            _S = S
            workers = workers or os.cpu_count() or 1
            chunks = np.array_split(self.coords, max(1, workers * 20))
            if workers > 1:
                with ProcessPoolExecutor(workers) as ex:
                    parts = list(ex.map(_work, [c for c in chunks if len(c)]))
            else:
                parts = [_work(c) for c in chunks if len(c)]
            self.packed = np.vstack(parts)
            self.prep_s = time.time() - t0
            if cache:
                np.savez_compressed(cache, coords=self.coords, packed=self.packed, prep_s=self.prep_s)
            log(f"  커버 지도: {len(self.coords)}칸 {self.prep_s:.0f}s (병렬 {workers})")
        self.n_pts = n_pts
        self.tree = cKDTree(self.coords)
        self.lo, self.hi = self.coords.min(0), self.coords.max(0)

    @classmethod
    def from_matrix(cls, cm):
        """이미 계산된 후보 커버리지 행렬(예: 교차점 195곳)로 '후보 = 그 지점들'인 지도 만들기 → 같은 후보에서 최적해와 공정 비교용"""
        o = cls.__new__(cls)
        o.S, o.step, o.buffer, o.prep_s = None, None, None, 0.0
        o.coords = np.asarray(cm.coords, float)
        o.packed = np.packbits(cm.M, axis=1)
        o.n_pts = cm.M.shape[1]
        o.tree = cKDTree(o.coords)
        o.lo, o.hi = o.coords.min(0), o.coords.max(0)
        d, _ = o.tree.query(o.coords, k=2)
        o.spacing = float(np.median(d[:, 1]))     # 후보 간 보통 간격 → 돌연변이 최소 폭 (이보다 작으면 다른 후보로 못 옮김)
        return o

    def snap(self, X):
        """연속 좌표 (K,2) → 가장 가까운 칸 번호와 그 칸 좌표"""
        _, idx = self.tree.query(X)
        return idx, self.coords[idx]

    def cover(self, idx):
        rows = np.unpackbits(self.packed[np.asarray(idx)], axis=1)[:, : self.n_pts]
        return rows.any(0).mean() * 100


class LatticeGA:
    def __init__(self, cl, K, pop=50, gens=150, n_elite=2, sigma_max=150.0, sigma_min=5.0, seed=0, init_pts=None):
        self.cl, self.K, self.pop, self.gens, self.n_elite = cl, K, pop, gens, n_elite
        self.smax, self.smin = sigma_max, sigma_min
        self.rng = np.random.default_rng(seed)
        self.init_pts = init_pts
        self.n_evals = 0
        self._memo = {}

    def fit(self, idx):
        key = tuple(sorted(int(i) for i in idx))
        if key not in self._memo:
            self.n_evals += 1
            self._memo[key] = self.cl.cover(list(key))
        return self._memo[key]

    def _init(self):
        if self.init_pts is not None:
            X = self.init_pts[self.rng.choice(len(self.init_pts), self.K, replace=False)]
        else:
            X = self.cl.coords[self.rng.choice(len(self.cl.coords), self.K, replace=False)]
        return self.cl.snap(X)[1]

    def crossover(self, A, fa, B, fb):
        D = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])
        r, c = linear_sum_assignment(D)
        w = fa / (fa + fb) if fa + fb > 0 else 0.5
        pick = self.rng.random(self.K) < w
        return np.where(pick[:, None], A[r], B[c])

    def mutate(self, X, g):
        sigma = self.smax - (self.smax - self.smin) * g / self.gens
        m = self.rng.random(self.K) < max(1.0 / self.K, 0.2)
        return X + m[:, None] * self.rng.normal(0, sigma, X.shape)

    def run(self):
        P = [self._init() for _ in range(self.pop)]
        I = [self.cl.snap(x)[0] for x in P]
        F = [self.fit(i) for i in I]
        curve = []
        for g in range(1, self.gens + 1):
            order = np.argsort(F)[::-1]
            curve.append(F[order[0]])
            if g == self.gens:
                break
            nP = [P[i] for i in order[: self.n_elite]]
            nI = [I[i] for i in order[: self.n_elite]]
            nF = [F[i] for i in order[: self.n_elite]]
            while len(nP) < self.pop:
                a = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])
                b = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])
                child = self.mutate(self.crossover(P[a], F[a], P[b], F[b]), g)
                idx, X = self.cl.snap(child)
                nP.append(X); nI.append(idx); nF.append(self.fit(idx))
            P, I, F = nP, nI, nF
        i = int(np.argmax(F))
        return P[i], F[i], curve
