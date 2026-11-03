#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_ga_continuous.py   (시뮬레이션 0회, 빠른 평가 모델)
================================================================
지난주 GA(algo4 하이브리드)의 연산은 그대로 두고 "개체 = K개 연속 좌표 그룹"으로만 바꾼 다중 RSU GA
  개체    : {(x1,y1), …, (xK,yK)}  연속 좌표 (지도 범위 안 어디든)
  적합도  : 빠른 평가 모델의 커버(서비스 비율 근사)   ※ PDR은 RSU를 한 점에 몰수록 유리해져서 다중 RSU에 부적합
  선택    : 토너먼트(무작위 3그룹 중 최고)로 부모 2개 + 엘리트 1그룹 유지        ← 지난주 algo4와 동일
  교배    : 부모 A, B의 RSU를 가장 가까운 것끼리 짝지음(헝가리안 매칭) → 짝마다 적합도 가중 평균
            child_i = (f_A·a_i + f_B·b_π(i)) / (f_A + f_B)
  돌연변이: 모든 좌표에 가우시안 노이즈 (Box-Muller: z = sqrt(−2 ln u1)·cos(2π u2))
            σ_g = σ_max − (σ_max − σ_min)·g/G,  σ_max=150m, σ_min=5m   ← 지난주 algo4와 동일
출력: experiment_results/step4/step4_ga_cont_placements.csv (→ step4_verify_sim.py 로 실측)
      step4_ga_cont_history.csv (세대별 모든 그룹), step4_ga_cont_curve.png
================================================================
"""
import argparse
import json
import math
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import linear_sum_assignment  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
from rsu_lib.surrogate import Surrogate  # noqa: E402

OUT = os.path.join("experiment_results", "step4")


def box_muller(rng, n):
    u1, u2 = rng.random(n), rng.random(n)
    return np.sqrt(-2 * np.log(np.maximum(u1, 1e-12))) * np.cos(2 * math.pi * u2)


class ContinuousGroupGA:
    def __init__(self, S, K, pop=20, gens=30, n_elite=1, sigma_max=150.0, sigma_min=5.0, seed=0, snap=5.0):
        self.S, self.K, self.pop, self.gens = S, K, pop, gens
        self.n_elite = n_elite
        self.sigma_max, self.sigma_min = sigma_max, sigma_min
        self.rng = np.random.default_rng(seed)
        self.lo = S.pts.min(0) - 50
        self.hi = S.pts.max(0) + 50
        self.snap = snap                  # 좌표를 5m 단위로 반올림해 같은 위치 재계산 방지(연속 좌표 근사)
        self.history, self.n_evals = [], 0

    def clip(self, X):
        X = np.clip(X, self.lo, self.hi)
        return np.round(X / self.snap) * self.snap

    def fit(self, X):
        self.n_evals += 1
        return self.S.cover_pct([tuple(p) for p in X])

    def crossover(self, A, fa, B, fb):
        D = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])
        r, c = linear_sum_assignment(D)
        w = fa / (fa + fb) if fa + fb > 0 else 0.5
        return w * A[r] + (1 - w) * B[c]

    def mutate(self, X, g):
        sigma = self.sigma_max - (self.sigma_max - self.sigma_min) * g / self.gens
        n = X.size
        return X + sigma * box_muller(self.rng, n).reshape(X.shape)

    def run(self):
        P = [self.clip(self.lo + self.rng.random((self.K, 2)) * (self.hi - self.lo)) for _ in range(self.pop)]
        F = [self.fit(x) for x in P]
        curve = []
        for g in range(1, self.gens + 1):
            for i, (x, f) in enumerate(zip(P, F)):
                self.history.append((g, i, round(f, 3), json.dumps(np.round(x, 1).tolist())))
            order = np.argsort(F)[::-1]
            curve.append(F[order[0]])
            if g == self.gens:
                break
            newP = [P[i] for i in order[: self.n_elite]]
            newF = [F[i] for i in order[: self.n_elite]]
            while len(newP) < self.pop:
                a = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])   # 토너먼트
                b = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])
                child = self.clip(self.mutate(self.crossover(P[a], F[a], P[b], F[b]), g))
                newP.append(child); newF.append(self.fit(child))
            P, F = newP, newF
        i = int(np.argmax(F))
        return P[i], F[i], curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ks", default="3,5,10")
    ap.add_argument("--pop", type=int, default=20, help="지난주 algo4는 10")
    ap.add_argument("--gens", type=int, default=30, help="지난주 algo4는 10")
    ap.add_argument("--runs", type=int, default=2)
    a = ap.parse_args()
    S = Surrogate("erlangen.poly.xml", "vehicle_snapshots_2s.csv")
    rows, hist, curves = [], [], {}
    for K in [int(k) for k in a.ks.split(",")]:
        best = None
        for run in range(a.runs):
            t = time.time()
            ga = ContinuousGroupGA(S, K, pop=a.pop, gens=a.gens, seed=run)
            x, f, curve = ga.run()
            curves[(K, run)] = curve
            hist += [dict(K=K, Run=run, Gen=g, Ind=i, Fitness=fv, Coords=c) for g, i, fv, c in ga.history]
            print(f"K={K} run{run}: {f:.2f}%  평가 {ga.n_evals}회  {time.time() - t:.0f}s  "
                  f"세대별 최고 {[round(v, 1) for v in curve[::max(1, a.gens // 8)]]}", flush=True)
            if best is None or f > best[1]:
                best = (x, f, ga.n_evals)
        rows.append(dict(Method="GA-연속좌표 (지난주 방식+그룹)", K=K, Coords=json.dumps(np.round(best[0], 2).tolist()),
                         Pred_Cover=round(best[1], 2), GA_evals=best[2], GA_runs=a.runs))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "step4_ga_cont_placements.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(hist).to_csv(os.path.join(OUT, "step4_ga_cont_history.csv"), index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for (K, run), c in curves.items():
        ax.plot(range(1, len(c) + 1), c, label=f"K={K} run{run}")
    ax.set_xlabel("Generation"); ax.set_ylabel("Best coverage (%)"); ax.grid(color="#e6e5e0")
    ax.set_title("Continuous-coordinate group GA convergence", loc="left", fontsize=11); ax.legend(frameon=False, fontsize=8)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_ga_cont_curve.png"), dpi=150)


if __name__ == "__main__":
    main()
