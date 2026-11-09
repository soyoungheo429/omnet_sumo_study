#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_placements.py   (VM, 시뮬레이션 0회 — 패턴마다 커버리지 행렬 처음 1회 수 분, 이후 캐시)
================================================================
교통 패턴(P1/P2/P3)별로 모든 방법의 RSU 배치를 만들고, 방법×K 계산 시간을 잰다.
방법 (8개)
  Grid top-K           : 150m 격자 340곳 각각 단독 커버 계산 → 점수 높은 순 K개 (다중 RSU 격자 비교군)
  Greedy-교차로        : algo1 수정 (교차로 111곳, 한계이득)
  Greedy-전체교차로    : algo7 수정 (교차점 195곳, 한계이득)
  GA-집합 (도로점)     : 개체 = K개 좌표 그룹, 도로 위 25m 간격 3,236곳
  GA-연속그룹          : 개체 = K개 연속 좌표 그룹, 후보·격자 없음. 지난주 algo4와 같은 토너먼트(3)·엘리트(1)·σ 150→5m,
                         교차는 짝지은 RSU 단위 균등 교차, 돌연변이는 RSU 단위, 첫 세대는 차량 위치에서 (--cga-ops/--cga-init)
  GA-연속그룹 (기존 연산): 이전 실행분(좌표 가중평균 교차 + 지도 전체 랜덤 초기화), --only-cga 때 이름만 바꿔 보존
  PPO / DQN            : 순차 배치 강화학습 (패턴마다 그 패턴 데이터로 따로 학습)
  최적해(ILP)          : 교차점 195곳 정수계획 (참고 상한)
시간 기록 (timing.csv)
  Prep_s   : 방법이 K와 상관없이 한 번 하는 준비 (후보지 커버리지 행렬 / 격자 점수 계산)
  Train_s  : 강화학습 학습 시간 (따로 표기)
  Time_K_s : 그 K 하나를 푸는 데 걸린 시간 (Greedy도 K마다 처음부터 다시 풀어서 잼)
출력: experiment_results/step5/<패턴>/placements.csv, timing.csv,
      fig_pred_cover_and_time.png (예측 커버·K별 시간), map_K5.png / map_K10.png (방법별 배치 지도)
실행: python3 -u step5_placements.py --patterns P1,P2,P3 2>&1 | tee step5_place_log.txt
      연속 GA만 다시: python3 -u step5_placements.py --only-cga 2>&1 | tee step5_cga_log.txt
================================================================
"""
import argparse
import json
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib.surrogate import Surrogate  # noqa: E402
from rsu_lib import candidates as CA  # noqa: E402
from rsu_lib.placement import CoverageMatrix, greedy_marginal, SetGA  # noqa: E402
from rsu_lib.rl import PPOAgent, DQNAgent  # noqa: E402

OUT = os.path.join("experiment_results", "step5")
KS = list(range(1, 11))


def cm_from(coords, M, ids=None):
    cm = object.__new__(CoverageMatrix)
    cm.coords, cm.M = np.asarray(coords, float), M
    cm.ids = ids or [f"c{i}" for i in range(len(coords))]
    cm.n_pts, cm.w = M.shape[1], np.ones(M.shape[1])
    cm.single = M.mean(1) * 100
    return cm


def build(S, pdir, force=False):
    cand = {"A": [(x, y) for _, x, y in CA.intersections("erlangen.net.xml")],
            "B": [(x, y) for _, x, y in CA.all_junctions("erlangen.net.xml")],
            "R": [tuple(p) for p in CA.road_points("erlangen.net.xml", 25)]}
    g = pd.read_csv("bruteforce_grid_150n_corrected.csv", encoding="utf-8-sig")
    cand["G"] = list(zip(g.Sim_X, g.Sim_Y))
    cache = os.path.join(pdir, "_coverage_cache.npz")
    if os.path.exists(cache) and not force:
        z = np.load(cache)
        mats = {k: np.unpackbits(z[k], axis=1)[:, : len(S.pts)].astype(bool) for k in cand}
        secs = json.loads(str(z["secs"]))
        print("  커버리지 행렬: 캐시 사용", {k: f"{v:.0f}s" for k, v in secs.items()})
    else:
        mats, secs = {}, {}
        for k, pts in cand.items():
            t = time.time()
            mats[k] = np.vstack([S.covered(p) for p in pts])
            secs[k] = time.time() - t
            print(f"  커버리지 행렬 {k}: {len(pts)}곳 {secs[k]:.0f}s", flush=True)
        np.savez_compressed(cache, secs=json.dumps(secs), **{k: np.packbits(v, axis=1) for k, v in mats.items()})
    return {k: cm_from(cand[k], mats[k]) for k in cand}, secs


def run_pattern(p, a):
    pdir = os.path.join(OUT, p)
    os.makedirs(pdir, exist_ok=True)
    snap = f"vehicle_snapshots_2s_{p}.csv"
    if not os.path.exists(snap):
        sys.exit(f"{snap} 없음 → 먼저 python3 step5_snapshots.py")
    print(f"\n===== {p} =====")
    S = Surrogate("erlangen.poly.xml", snap)
    if a.only_cga:
        return rerun_cga(S, p, pdir, a)
    cms, secs = build(S, pdir, a.force_matrix)
    A, B, R, G = cms["A"], cms["B"], cms["R"], cms["G"]
    place, timing = [], []

    def add(m, K, coords, t):
        coords = [[round(float(x), 2), round(float(y), 2)] for x, y in coords]
        place.append(dict(Pattern=p, Method=m, K=K, Coords=json.dumps(coords),
                          Pred_Cover=round(S.cover_pct([tuple(c) for c in coords]), 2), Time_K_s=round(t, 4)))

    def tick():
        return time.perf_counter()

    # 1) Grid top-K
    for K in KS:
        t = tick(); sel = list(np.argsort(-G.single, kind="stable")[:K]); add("Grid top-K", K, G.coords[sel], tick() - t)
    timing.append(dict(Method="Grid top-K", Prep_s=secs["G"], Train_s=0))
    # 2,3) Greedy
    for cm, lab, key in ((A, "Greedy-교차로", "A"), (B, "Greedy-전체교차로", "B")):
        for K in KS:
            t = tick(); sel = greedy_marginal(cm, K)[0]; add(lab, K, cm.coords[sel], tick() - t)
        timing.append(dict(Method=lab, Prep_s=secs[key], Train_s=0))
    # 4) 집합 GA
    for K in KS:
        t = tick(); best = None
        for run in range(a.ga_runs):
            ind, f, _ = SetGA(R, K, pop=40, gens=60, seed=run).run()
            if best is None or f > best[1]:
                best = (ind, f)
        add("GA-집합 (도로점)", K, R.coords[best[0]], tick() - t)
        print(f"  Set-GA K={K}: {best[1]:.2f}%", flush=True)
    timing.append(dict(Method="GA-집합 (도로점)", Prep_s=secs["R"], Train_s=0))
    # 5) 연속 그룹 GA (격자·후보 없음, 개체 = K개 연속 좌표, 첫 세대는 차량 위치에서)
    if a.cga_ks:
        for K, X, sec in cga(S, a):
            add("GA-연속그룹", K, X, sec)
        timing.append(dict(Method="GA-연속그룹", Prep_s=0, Train_s=0))
    # 6,7) RL — 그 패턴의 앞 70% 시간대 30장 창 12개로 학습
    sn = S.snap.snapshot_no.to_numpy()
    cut = np.quantile(sn, 0.7)
    rng = np.random.default_rng(0)
    train = []
    for _ in range(12):
        s0 = rng.integers(sn.min(), cut - 30)
        train.append(B.subset_points((sn >= s0) & (sn < s0 + 30)))
    for lab, Ag, kw in (("PPO", PPOAgent, dict(iters=a.ppo_iters, episodes=8, log_every=0)),
                        ("DQN", DQNAgent, dict(episodes=a.dqn_eps, log_every=0))):
        ag = Ag(seed=0)
        t = tick(); ag.train(train, **kw); tr = tick() - t
        print(f"  {lab} 학습 {tr:.1f}s", flush=True)
        for K in KS:
            t = tick()
            sel = ag.run_episode(B, K, greedy=True)[0] if lab == "PPO" else ag.run_episode(B, K)[0]
            add(lab, K, B.coords[sel], tick() - t)
        timing.append(dict(Method=lab, Prep_s=secs["B"], Train_s=tr))
    # 8) 최적해
    try:
        from rsu_lib.optimal import max_cover_optimal
        for K in KS:
            t = tick(); sel = max_cover_optimal(B, K, 60)[0]; add("최적해(ILP)", K, B.coords[sel], tick() - t)
        timing.append(dict(Method="최적해(ILP)", Prep_s=secs["B"], Train_s=0))
    except Exception as e:
        print("  (최적해 생략:", e, ")")

    save(S, pd.DataFrame(place), pd.DataFrame(timing), p, pdir)


def cga(S, a):
    from step4_ga_continuous import ContinuousGroupGA
    for K in [int(k) for k in a.cga_ks.split(",")]:
        t = time.perf_counter(); best = None
        for run in range(a.cga_runs):
            X, f, _ = ContinuousGroupGA(S, K, pop=a.cga_pop, gens=a.cga_gens, seed=run, init=a.cga_init, ops=a.cga_ops).run()
            if best is None or f > best[1]:
                best = (X, f)
        sec = time.perf_counter() - t
        print(f"  연속 GA K={K}: {best[1]:.2f}%  {sec:.0f}s", flush=True)
        yield K, best[0], sec


def rerun_cga(S, p, pdir, a):
    """연속 그룹 GA만 다시: 기존 결과는 'GA-연속그룹 (기존 연산)'로 이름만 바꿔 남김"""
    P = pd.read_csv(os.path.join(pdir, "placements.csv"), encoding="utf-8-sig")
    T = pd.read_csv(os.path.join(pdir, "timing.csv"), encoding="utf-8-sig")[["Method", "Prep_s", "Train_s"]]
    old = "GA-연속그룹 (기존 연산)"
    if old not in set(P.Method):
        P.loc[P.Method == "GA-연속그룹", "Method"] = old
        T.loc[T.Method == "GA-연속그룹", "Method"] = old
    P = P[P.Method != "GA-연속그룹"]
    T = T[T.Method != "GA-연속그룹"]
    rows = []
    for K, X, sec in cga(S, a):
        c = [[round(float(x), 2), round(float(y), 2)] for x, y in X]
        rows.append(dict(Pattern=p, Method="GA-연속그룹", K=K, Coords=json.dumps(c),
                         Pred_Cover=round(S.cover_pct([tuple(q) for q in c]), 2), Time_K_s=round(sec, 4)))
    P = pd.concat([P, pd.DataFrame(rows)], ignore_index=True)
    T = pd.concat([T, pd.DataFrame([dict(Method="GA-연속그룹", Prep_s=0, Train_s=0)])], ignore_index=True)
    save(S, P, T, p, pdir)


def save(S, P, T, p, pdir):
    P.to_csv(os.path.join(pdir, "placements.csv"), index=False, encoding="utf-8-sig")
    tk = P.pivot_table(index="Method", columns="K", values="Time_K_s")
    tk.columns = [f"K{k}_s" for k in tk.columns]
    T = T.merge(tk, left_on="Method", right_index=True, how="left")
    T["Sum_K_s"] = tk.sum(axis=1).reindex(T.Method).to_numpy()
    T["Total_s"] = T.Prep_s + T.Train_s + T.Sum_K_s
    T.round(4).to_csv(os.path.join(pdir, "timing.csv"), index=False, encoding="utf-8-sig")
    figures(S, P, T, p, pdir)
    print(P.pivot_table(index="K", columns="Method", values="Pred_Cover").round(1).to_string())
    print(T[["Method", "Prep_s", "Train_s", "Sum_K_s", "Total_s"]].round(2).to_string(index=False))


EN = {"GA-연속그룹 (기존 연산)": "Continuous group-GA (old operators)", "Grid top-K": "Grid top-K", "Greedy-교차로": "Greedy-intersection", "Greedy-전체교차로": "Greedy-all junctions",
      "GA-집합 (도로점)": "Set-GA", "GA-연속그룹": "Continuous group-GA", "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "ILP (optimal)"}
COL = {"GA-연속그룹 (기존 연산)": "#f3d27a", "Grid top-K": "#8d8c86", "Greedy-교차로": "#2a6fdb", "Greedy-전체교차로": "#1b998b", "GA-집합 (도로점)": "#eb6834",
       "GA-연속그룹": "#e3a008", "PPO": "#8e44ad", "DQN": "#c0392b", "최적해(ILP)": "#0b0b0b"}


def figures(S, P, T, p, pdir):
    """예측 커버 곡선, K별 계산 시간, K=5/10 배치 지도 (방법별)"""
    ms = [m for m in EN if m in set(P.Method)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    for m in ms:
        s = P[P.Method == m].sort_values("K")
        axes[0].plot(s.K, s.Pred_Cover, marker="o", ms=3.5, lw=1.6, color=COL[m], label=EN[m],
                     ls=":" if m == "최적해(ILP)" else "-")
        axes[1].plot(s.K, s.Time_K_s.clip(lower=1e-5), marker="o", ms=3.5, lw=1.6, color=COL[m], label=EN[m])
    axes[0].set_ylabel("Predicted coverage ≈ service ratio (%)"); axes[0].set_title(f"{p}: coverage by method", loc="left", fontsize=11)
    axes[1].set_yscale("log"); axes[1].set_ylabel("Time to solve one K (s, log)")
    axes[1].set_title(f"{p}: computation time per K (RL training excluded)", loc="left", fontsize=11)
    for ax in axes:
        ax.set_xlabel("K"); ax.grid(color="#e6e5e0")
    axes[0].legend(frameon=False, fontsize=8)
    plt.tight_layout(); plt.savefig(os.path.join(pdir, "fig_pred_cover_and_time.png"), dpi=150); plt.close()
    for K in (5, 10):
        sub = [m for m in ms if not P[(P.Method == m) & (P.K == K)].empty]
        nc = 4
        nr = int(np.ceil(len(sub) / nc))
        fig, axes = plt.subplots(nr, nc, figsize=(4.2 * nc, 4.6 * nr), sharex=True, sharey=True)
        axes = np.atleast_1d(axes).ravel()
        for ax, m in zip(axes, sub):
            row = P[(P.Method == m) & (P.K == K)].iloc[0]
            c = np.array(json.loads(row.Coords))
            cov = np.zeros(len(S.pts), bool)
            for q in c:
                cov |= S.covered(tuple(q))
            ax.scatter(S.pts[~cov, 0], S.pts[~cov, 1], s=1.5, color="#d8d7d2")
            ax.scatter(S.pts[cov, 0], S.pts[cov, 1], s=1.5, color="#9cc3f0")
            ax.scatter(c[:, 0], c[:, 1], s=60, marker="X", color=COL[m], edgecolor="#0b0b0b", lw=0.6, zorder=5)
            ax.set_title(f"{EN[m]}: {row.Pred_Cover:.1f}%", fontsize=9, loc="left")
            ax.set_xlim(0, 2660); ax.set_ylim(3060, 0); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for ax in axes[len(sub):]:
            ax.axis("off")
        fig.suptitle(f"{p}, K={K} placements (blue = vehicle positions covered, grey = not covered)", x=0.01, ha="left", fontsize=10)
        plt.tight_layout(); plt.savefig(os.path.join(pdir, f"map_K{K}.png"), dpi=140); plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns", default="P1,P2,P3")
    ap.add_argument("--force-matrix", action="store_true")
    ap.add_argument("--ga-runs", type=int, default=2)
    ap.add_argument("--cga-ks", default="1,2,3,4,5,6,7,8,9,10", help="연속 GA 돌릴 K (빈 문자열이면 생략)")
    ap.add_argument("--cga-init", default="vehicles", choices=["vehicles", "uniform"],
                    help="첫 세대: vehicles=차량 위치에서 K개 / uniform=지도 전체 랜덤(지난주 algo4)")
    ap.add_argument("--cga-ops", default="gene", choices=["gene", "avg"],
                    help="gene=RSU 단위 균등 교차·돌연변이 / avg=좌표 가중평균 교차(지난주 algo4)")
    ap.add_argument("--only-cga", action="store_true", help="연속 그룹 GA만 다시 돌려 기존 placements.csv에 반영")
    ap.add_argument("--cga-runs", type=int, default=2, help="집합 GA와 같게 2회 중 최고")
    ap.add_argument("--cga-pop", type=int, default=20)
    ap.add_argument("--cga-gens", type=int, default=30)
    ap.add_argument("--ppo-iters", type=int, default=120)
    ap.add_argument("--dqn-eps", type=int, default=1200)
    a = ap.parse_args()
    t0 = time.time()
    for p in a.patterns.split(","):
        run_pattern(p, a)
    print(f"\n완료 {time.time() - t0:.0f}s → {OUT}/<패턴>/placements.csv  다음: step5_verify_sim.py")


if __name__ == "__main__":
    main()
