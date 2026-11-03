# -*- coding: utf-8 -*-
"""rsu_lib/optimal.py — 최대 커버리지 정수계획(MCLP) 최적해 (scipy HiGHS). 알고리즘들의 '최적 대비 몇 %' 기준선용."""
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import csr_matrix, hstack, vstack, eye


def max_cover_optimal(cm, K, time_limit=120):
    M = cm.M
    # 같은 커버 패턴의 점들은 하나로 묶기 (가중치 합)
    cols, inv = np.unique(M.T, axis=0, return_inverse=True)
    w = np.bincount(inv.ravel(), weights=cm.w)
    keep = cols.any(1)                         # 아무도 못 덮는 점 제외
    cols, w = cols[keep], w[keep]
    C, P = M.shape[0], len(w)
    # 변수: x (C개, 이진) + y (P개, 0~1)   목적: max w·y  →  min −w·y
    c = np.r_[np.zeros(C), -w]
    A1 = hstack([-csr_matrix(cols.astype(float)), eye(P)])      # y_j − Σ x_i ≤ 0
    A2 = csr_matrix(np.r_[np.ones(C), np.zeros(P)][None, :])    # Σ x = K
    cons = [LinearConstraint(A1, -np.inf, 0), LinearConstraint(A2, K, K)]
    integ = np.r_[np.ones(C), np.zeros(P)]
    res = milp(c, constraints=cons, integrality=integ, bounds=Bounds(0, 1),
               options={"time_limit": time_limit, "disp": False})
    x = res.x[:C] if res.x is not None else np.zeros(C)
    sel = list(np.argsort(-x)[:K])
    return sel, cm.cover(sel), res.status, getattr(res, "mip_gap", None)
