#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step7_budget_test.py — 연속 GA v3 탐색 예산(개체 × 세대 × 반복)별 성능·시간 비교 (시뮬레이션 0회)
  저장된 커버 지도(_lattice_5m_30m.npz)를 써서 몇 분이면 끝남. 최적해(교차점 ILP)도 같이 표시.
실행: python3 step7_budget_test.py --pattern DA_P1
출력: experiment_results/step5/<패턴>/budget_test.csv
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib import scenario as SC  # noqa: E402
from rsu_lib import candidates as CA  # noqa: E402
from rsu_lib.surrogate import Surrogate  # noqa: E402
from rsu_lib.lattice_ga import CoverLattice, LatticeGA  # noqa: E402
from rsu_lib.placement import CoverageMatrix  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pattern", default="DA_P1")
ap.add_argument("--ks", default="5,8,10")
ap.add_argument("--budgets", default="50x150x6,100x300x6,200x400x6,300x600x6")
a = ap.parse_args()
F = SC.use(a.pattern)
pdir = os.path.join("experiment_results", "step5", a.pattern)
S = Surrogate(F["poly"], F["snap"])
cl = CoverLattice(S, F["net"], cache=os.path.join(pdir, "_lattice_5m_30m.npz"))
ks = [int(k) for k in a.ks.split(",")]
ilp = {}
try:
    from rsu_lib.optimal import max_cover_optimal
    B = CoverageMatrix(S, [(x, y) for _, x, y in CA.all_junctions(F["net"])])
    for K in ks:
        ilp[K] = max_cover_optimal(B, K, 120)[1]
    print("최적해(교차점 ILP):", {K: round(v, 2) for K, v in ilp.items()}, flush=True)
except Exception as e:
    print("(최적해 생략:", e, ")")
rows = []
for b in a.budgets.split(","):
    pop, gens, runs = (int(x) for x in b.split("x"))
    for K in ks:
        t = time.time(); best = 0
        for r in range(runs):
            best = max(best, LatticeGA(cl, K, pop=pop, gens=gens, seed=r, init_pts=S.pts).run()[1])
        rows.append(dict(Budget=b, K=K, Cover=round(best, 2), ILP=round(ilp.get(K, np.nan), 2), Sec=round(time.time() - t, 1)))
        print(f"{b:>12}  K={K:2d}  GA {best:6.2f}%  (최적해 {ilp.get(K, float('nan')):6.2f}%)  {time.time() - t:6.1f}s", flush=True)
pd.DataFrame(rows).to_csv(os.path.join(pdir, "budget_test.csv"), index=False, encoding="utf-8-sig")
print("저장:", os.path.join(pdir, "budget_test.csv"))
