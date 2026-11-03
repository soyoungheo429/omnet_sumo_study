#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_fixed_algorithms.py   (시뮬레이션 0회, 빠른 평가 모델만 사용)
================================================================
랩미팅 코멘트 반영
  (2) algo1/algo7 성능 엎치락뒤치락 → 원인 진단 + "한계이득 Greedy"로 수정
  (1) 다중 RSU GA: 개체 = K개 좌표 집합(그룹), 부모 그룹 → 자식 그룹
  (3) 강화학습: PPO(Greta, TMC'24 방식), DQN(GCOMB, NeurIPS'20 방식) 순차 배치

평가: rsu_lib/surrogate.py (Veins 전파 모델 재현, 격자 340곳 실측 PDR과 r=0.984)
출력: experiment_results/step4/
  step4_surrogate_validation.csv/png   근사 모델 vs 실측(격자 340 + step2 단독 32)
  step4_old_diagnosis.csv              기존 algo1/algo7: K별 단독커버·새로덮는양(한계이득)
  step4_placements.csv                 방법×K 별 RSU 좌표 (→ step4_verify_sim.py 로 실제 시뮬 검증)
  step4_summary.csv                    방법×K 별 예측 커버(서비스 비율 근사)
  step4_ga_generations.csv             GA 세대별 모든 그룹(좌표 K개) 기록
  step4_*.png                          그림
실행:  python3 step4_fixed_algorithms.py            (처음 1회는 커버리지 행렬 계산 몇 분, 이후 캐시)
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
from rsu_lib.placement import CoverageMatrix, greedy_marginal, swap_local_search, SetGA  # noqa: E402
from rsu_lib.rl import PPOAgent, DQNAgent  # noqa: E402

OUT = os.path.join("experiment_results", "step4")
CACHE = os.path.join(OUT, "_coverage_cache.npz")
KS = list(range(1, 11))
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
COL = {"algo1 (기존)": "#b9b8b2", "algo7 (기존)": "#8d8c86", "Greedy-교차로 (algo1 수정)": "#2a6fdb",
       "Greedy-전체교차로 (algo7 수정)": "#1b998b", "GA-집합 (도로점)": "#eb6834", "PPO": "#8e44ad", "DQN": "#c0392b",
       "최적해(ILP)": INK}
EN = {"algo1 (기존)": "algo1 (old)", "algo7 (기존)": "algo7 (old)", "Greedy-교차로 (algo1 수정)": "Greedy-intersection (algo1 fixed)",
      "Greedy-전체교차로 (algo7 수정)": "Greedy-all junctions (algo7 fixed)", "GA-집합 (도로점)": "Set-GA (road points)",
      "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "Optimal (ILP)"}


def build_matrices(S, force=False):
    A = CA.intersections("erlangen.net.xml")
    B = CA.all_junctions("erlangen.net.xml")
    R = CA.road_points("erlangen.net.xml", 25)
    if os.path.exists(CACHE) and not force:
        z = np.load(CACHE)
        mats = {k: np.unpackbits(z[k], axis=1)[:, : len(S.pts)].astype(bool) for k in ("A", "B", "R")}
    else:
        print("커버리지 행렬 계산 중 (처음 1회, 수 분)...", flush=True)
        mats = {}
        for k, pts in (("A", [(x, y) for _, x, y in A]), ("B", [(x, y) for _, x, y in B]), ("R", R)):
            t = time.time()
            mats[k] = np.vstack([S.covered(tuple(p)) for p in pts])
            print(f"  {k}: {len(pts)}곳 {time.time() - t:.0f}s", flush=True)
        np.savez_compressed(CACHE, **{k: np.packbits(v, axis=1) for k, v in mats.items()})
    out = {}
    for k, pts, ids in (("A", [(x, y) for _, x, y in A], [i for i, _, _ in A]),
                        ("B", [(x, y) for _, x, y in B], [i for i, _, _ in B]),
                        ("R", [tuple(p) for p in R], None)):
        cm = object.__new__(CoverageMatrix)
        cm.coords, cm.ids, cm.M = np.asarray(pts, float), ids or [f"r{i}" for i in range(len(pts))], mats[k]
        cm.n_pts, cm.w = cm.M.shape[1], np.ones(cm.M.shape[1])
        cm.single = cm.M.mean(1) * 100
        out[k] = cm
    return out


def validate(S):
    rows = []
    g = pd.read_csv("bruteforce_grid_150n_corrected.csv", encoding="utf-8-sig")
    for x, y, p in zip(g.Sim_X, g.Sim_Y, g.PDR):
        rows.append(dict(Source="grid150_PDR", Sim_X=x, Sim_Y=y, Measured=p, Predicted=S.cover_pct([(x, y)])))
    p2 = os.path.join("experiment_results", "step2", "step2_runs_raw.csv")
    if os.path.exists(p2):
        r = pd.read_csv(p2)
        r = r[(r.Phase == "isolated") & (r.Sync.astype(str) == "True") & (r.Success.astype(str) == "True")]
        for c, sv, rs in zip(r.RSU_Coords, r.Service_Ratio, r.RSSI_Mean_dBm):
            x, y = json.loads(c)[0]
            ev = S.evaluate([(x, y)])
            rows.append(dict(Source="step2_isolated_Service", Sim_X=x, Sim_Y=y, Measured=sv, Predicted=ev["Cover_pct"],
                             RSSI_meas=rs, RSSI_pred=ev["RSSI_mean_pred"]))
    v = pd.DataFrame(rows)
    v.to_csv(os.path.join(OUT, "step4_surrogate_validation.csv"), index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(5.2, 5))
    for src, c, m in (("grid150_PDR", "#2a6fdb", "o"), ("step2_isolated_Service", "#eb6834", "s")):
        s = v[v.Source == src]
        r = np.corrcoef(s.Measured, s.Predicted)[0, 1]
        ax.scatter(s.Measured, s.Predicted, s=16, color=c, marker=m, alpha=0.7,
                   label=f"{'Grid 340 (PDR)' if src.startswith('grid') else 'step2 isolated 32 (service ratio)'}  r={r:.3f}")
    lim = max(v.Measured.max(), v.Predicted.max()) + 2
    ax.plot([0, lim], [0, lim], color=MUTED, lw=1, ls="--")
    ax.set_xlabel("Measured in OMNeT++/Veins (%)"); ax.set_ylabel("Surrogate prediction (%)")
    ax.set_title("Surrogate vs simulation (single RSU)", loc="left", fontsize=11)
    ax.grid(color=GRID); ax.legend(frameon=False, fontsize=8, loc="upper left")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_surrogate_validation.png"), dpi=150); plt.close()
    for src in v.Source.unique():
        s = v[v.Source == src]
        print(f"  {src:24s} n={len(s):3d}  r={np.corrcoef(s.Measured, s.Predicted)[0, 1]:.3f}  "
              f"평균오차={np.mean(np.abs(s.Measured - s.Predicted)):.2f}%p")


def diagnose_old(S):
    rows = []
    for name, f in (("algo1", "final_selected_rsus_algo1_corrected.csv"), ("algo7", "final_selected_rsus_corrected.csv")):
        d = pd.read_csv(f, encoding="utf-8-sig").sort_values("Rank").head(10)
        cum = np.zeros(len(S.pts), bool)
        for k, (x, y) in enumerate(zip(d.Sim_X, d.Sim_Y), 1):
            c = S.covered((x, y))
            rows.append(dict(Algo=name, K=k, Sim_X=x, Sim_Y=y, Alone_pct=round(100 * c.mean(), 2),
                             New_pct=round(100 * (c & ~cum).mean(), 2), Cum_pct=round(100 * (cum | c).mean(), 2)))
            cum |= c
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "step4_old_diagnosis.csv"), index=False, encoding="utf-8-sig")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-matrix", action="store_true")
    ap.add_argument("--ga-runs", type=int, default=2)
    ap.add_argument("--quick", action="store_true", help="RL 학습을 짧게 (테스트용)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    S = Surrogate("erlangen.poly.xml", "vehicle_snapshots_2s.csv")
    print("[1] 근사 모델 검증"); validate(S)
    print("[2] 기존 algo1/algo7 진단"); old = diagnose_old(S)
    print(old.pivot(index="K", columns="Algo", values="New_pct").rename(columns=lambda c: c + " 새로덮은%").to_string())
    cms = build_matrices(S, a.force_matrix)
    A, B, R = cms["A"], cms["B"], cms["R"]

    place, summ, curves = [], [], {}

    def add(method, K, coords, pred, extra=None):
        place.append(dict(Method=method, K=K, Coords=json.dumps([[round(float(x), 2), round(float(y), 2)] for x, y in coords]),
                          Pred_Cover=round(pred, 2), **(extra or {})))

    # 기존
    for name, lab in (("algo1", "algo1 (기존)"), ("algo7", "algo7 (기존)")):
        d = old[old.Algo == name]
        for K in KS:
            s = d[d.K <= K]
            add(lab, K, list(zip(s.Sim_X, s.Sim_Y)), float(s.Cum_pct.iloc[-1]))
    # Greedy 수정판 (중첩 해: K+1 = K + 1개)
    print("[3] 한계이득 Greedy")
    for cm, lab in ((A, "Greedy-교차로 (algo1 수정)"), (B, "Greedy-전체교차로 (algo7 수정)")):
        sel, cums, gains = greedy_marginal(cm, max(KS))
        for K in KS:
            add(lab, K, cm.coords[sel[:K]], cums[K - 1], {"Marginal_gain": round(gains[K - 1], 2)})
        print(f"  {lab}: 누적 {[round(c, 1) for c in cums]}")
    # 최적해 (참고)
    try:
        from rsu_lib.optimal import max_cover_optimal
        for K in KS:
            sel, val, st, _ = max_cover_optimal(B, K, 60)
            add("최적해(ILP)", K, B.coords[sel], val)
    except Exception as e:  # scipy 버전에 milp 없으면 생략
        print("  (최적해 생략:", e, ")")
    # GA
    print("[4] 집합 GA (개체 = K개 좌표 그룹, 도로점 후보)")
    hist_rows = []
    for K in KS:
        best = None
        for run in range(a.ga_runs):
            ga = SetGA(R, K, pop=40, gens=60, seed=run)
            ind, f, curve = ga.run()
            curves[("GA", K, run)] = curve
            for g, i, fit, idx in ga.history:
                if K in (3, 5, 10) and run == 0:
                    hist_rows.append(dict(K=K, Run=run, Gen=g, Ind=i, Fitness=round(fit, 3),
                                          Coords=json.dumps([[round(float(R.coords[j][0]), 1), round(float(R.coords[j][1]), 1)] for j in idx])))
            if best is None or f > best[1]:
                best = (ind, f, run, ga.n_evals)
        add("GA-집합 (도로점)", K, R.coords[best[0]], best[1], {"GA_evals": best[3], "GA_runs": a.ga_runs})
        print(f"  K={K:2d}: {best[1]:.2f}%  (평가 {best[3]}회 × {a.ga_runs} run)")
    pd.DataFrame(hist_rows).to_csv(os.path.join(OUT, "step4_ga_generations.csv"), index=False, encoding="utf-8-sig")

    # RL
    print("[5] 강화학습 (PPO, DQN) — 학습: 앞 70% 시간대의 60초 창들 / 평가: 전체")
    snap = pd.read_csv("vehicle_snapshots_2s.csv", encoding="utf-8-sig")
    sn = snap.snapshot_no.to_numpy()
    cut = np.quantile(sn, 0.7)
    rng = np.random.default_rng(0)
    train = []
    for _ in range(12):
        s0 = rng.integers(sn.min(), cut - 30)
        train.append(B.subset_points((sn >= s0) & (sn < s0 + 30)))
    test = B.subset_points(sn >= cut)
    ppo = PPOAgent(seed=0)
    curves["PPO"] = ppo.train(train, iters=40 if a.quick else 120, episodes=8, log_every=20)
    dqn = DQNAgent(seed=0)
    curves["DQN"] = dqn.train(train, episodes=300 if a.quick else 1200, log_every=200)
    rl_rows = []
    for K in KS:
        for lab, ag in (("PPO", ppo), ("DQN", dqn)):
            sel = ag.run_episode(B, K, greedy=True)[0] if lab == "PPO" else ag.run_episode(B, K)[0]
            add(lab, K, B.coords[sel], B.cover(sel))
            st = ag.run_episode(test, K, greedy=True)[0] if lab == "PPO" else ag.run_episode(test, K)[0]
            rl_rows.append(dict(Method=lab, K=K, Test_cover=round(test.cover(st), 2)))
        rl_rows.append(dict(Method="Greedy", K=K, Test_cover=round(test.cover(greedy_marginal(test, K)[0]), 2)))
    pd.DataFrame(rl_rows).to_csv(os.path.join(OUT, "step4_rl_heldout.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame({"iter": range(1, len(curves["PPO"]) + 1), "PPO_minus_greedy": curves["PPO"]}).to_csv(
        os.path.join(OUT, "step4_rl_ppo_curve.csv"), index=False)
    pd.DataFrame({"episode": range(1, len(curves["DQN"]) + 1), "DQN_minus_greedy": curves["DQN"]}).to_csv(
        os.path.join(OUT, "step4_rl_dqn_curve.csv"), index=False)

    P = pd.DataFrame(place)
    P.to_csv(os.path.join(OUT, "step4_placements.csv"), index=False, encoding="utf-8-sig")
    piv = P.pivot_table(index="K", columns="Method", values="Pred_Cover")
    piv.to_csv(os.path.join(OUT, "step4_summary.csv"), encoding="utf-8-sig")
    print("\n예측 커버(%) — 서비스 비율 근사")
    print(piv.round(1).to_string())

    # ---------- 그림 ----------
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    for m in [c for c in COL if c in piv.columns]:
        ls = "--" if "기존" in m else ("-" if m != "최적해(ILP)" else ":")
        ax.plot(piv.index, piv[m], marker="o", ms=3.5, lw=1.8, ls=ls, color=COL[m], label=EN[m])
    ax.set_xlabel("K (number of RSUs)"); ax.set_ylabel("Predicted coverage ≈ service ratio (%)")
    ax.set_title("Coverage by method", loc="left", fontsize=11); ax.grid(color=GRID); ax.legend(frameon=False, fontsize=8)
    ax = axes[1]
    w = 0.38
    for j, (nm, lab, c) in enumerate((("algo1", "algo1 (old order)", "#b9b8b2"), ("algo7", "algo7 (old order)", "#8d8c86"))):
        s = old[old.Algo == nm]
        ax.bar(s.K + (j - 1) * w / 1.0 - w / 2 + w / 2, s.New_pct, width=w / 1.05, color=c, label=lab)
    gsel = P[P.Method == "Greedy-교차로 (algo1 수정)"]
    ax.plot(gsel.K, gsel.Marginal_gain, color="#2a6fdb", marker="o", lw=2, label="Greedy fixed (always decreasing)")
    ax.set_xlabel("k-th RSU added"); ax.set_ylabel("New coverage added by this RSU (%p)")
    ax.set_title("Why curves zig-zag: marginal gain of each added RSU", loc="left", fontsize=11)
    ax.grid(color=GRID, axis="y"); ax.legend(frameon=False, fontsize=8); ax.set_xticks(KS)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_methods_and_marginal.png"), dpi=150); plt.close()

    # GA 세대별 그룹 (K=5)
    h = pd.DataFrame(hist_rows)
    if len(h):
        hk = h[(h.K == 5)]
        gens = sorted(hk.Gen.unique())
        show = [gens[0], gens[2], gens[9], gens[29], gens[-1]]
        fig, axes = plt.subplots(1, len(show), figsize=(3.3 * len(show), 3.6), sharex=True, sharey=True)
        for ax, g in zip(axes, show):
            sg = hk[hk.Gen == g].sort_values("Fitness", ascending=False)
            ax.scatter(S.pts[:, 0], S.pts[:, 1], s=1, color="#d8d7d2")
            for _, row in sg.iloc[1:].iterrows():
                c = np.array(json.loads(row.Coords))
                ax.scatter(c[:, 0], c[:, 1], s=6, color="#f2b9a1", alpha=0.5)
            c = np.array(json.loads(sg.iloc[0].Coords))
            ax.scatter(c[:, 0], c[:, 1], s=45, color="#eb6834", edgecolor=INK, lw=0.6, zorder=5)
            ax.set_title(f"Gen {g}: best group {sg.iloc[0].Fitness:.1f}%", fontsize=9, loc="left")
            ax.set_ylim(sim_ymax := S.pts[:, 1].max() + 100, S.pts[:, 1].min() - 100); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
        fig.suptitle("Set-GA (K=5): each individual = a group of 5 RSUs (orange = best group, light = other groups)", fontsize=10, x=0.01, ha="left")
        plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_ga_groups_by_generation.png"), dpi=150); plt.close()

    # RL 학습곡선
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, key, xl in ((axes[0], "PPO", "PPO iteration"), (axes[1], "DQN", "DQN episode")):
        y = pd.Series(curves[key]).rolling(10 if key == "PPO" else 50, min_periods=1).mean()
        ax.plot(y.index + 1, y, color=COL[key]); ax.axhline(0, color=MUTED, ls="--", lw=1)
        ax.set_xlabel(xl); ax.set_ylabel("RL − Greedy (%p)"); ax.grid(color=GRID)
        ax.set_title(f"{key}: learns to match greedy", loc="left", fontsize=11)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_rl_training.png"), dpi=150); plt.close()

    # 지도: K=5 배치 비교
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.4), sharex=True, sharey=True)
    for ax, m in zip(axes, ["algo1 (기존)", "algo7 (기존)", "Greedy-교차로 (algo1 수정)", "GA-집합 (도로점)"]):
        row = P[(P.Method == m) & (P.K == 5)].iloc[0]
        c = np.array(json.loads(row.Coords))
        cov = np.zeros(len(S.pts), bool)
        for p in c:
            cov |= S.covered(tuple(p))
        ax.scatter(S.pts[~cov, 0], S.pts[~cov, 1], s=2, color="#d8d7d2")
        ax.scatter(S.pts[cov, 0], S.pts[cov, 1], s=2, color="#9cc3f0")
        ax.scatter(c[:, 0], c[:, 1], s=70, marker="X", color=COL[m], edgecolor=INK, lw=0.6, zorder=5)
        for i, p in enumerate(c, 1):
            ax.annotate(str(i), p, xytext=(4, 4), textcoords="offset points", fontsize=8)
        ax.set_title(f"{EN[m]}  K=5: {row.Pred_Cover:.1f}%", fontsize=9, loc="left")
        ax.set_ylim(S.pts[:, 1].max() + 100, S.pts[:, 1].min() - 100); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("K=5 placements (blue = vehicle positions covered, grey = not covered, numbers = order added)", fontsize=10, x=0.01, ha="left")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_k5_maps.png"), dpi=150); plt.close()
    print(f"\n완료 {time.time() - t0:.0f}s → {OUT}")


if __name__ == "__main__":
    main()
