#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_analyze.py   (시뮬레이션 0회, 몇 초 — step5_verify_sim.py 결과로 표·그래프·검정)
================================================================
교수님 코멘트 반영
  - 모든 결과: 반복 횟수 n, 평균, 표준편차(, 95% 신뢰구간)
  - 여러 지표를 같이 볼 때 어떤 방법이 제일 좋은가 → 종합 점수(정규화 평균) + TOPSIS, 시나리오(패턴×K)마다 순위 → 평균 순위
  - 지표를 하나씩 더해가며 순위가 어떻게 바뀌는지 (서비스 → +PDR → ... → +계산 시간)
  - 방법별 K당 시간·전체 시간, 강화학습 학습 시간은 따로
  - 유의성: 시나리오별 최고 방법 vs 나머지 (같은 seed끼리 짝지은 t검정), 전체는 Friedman 검정
출력: experiment_results/step5/analysis/
  table_mean_std.csv/.md        패턴×K×방법, 모든 지표 "평균 ± 표준편차 (n)"
  composite_by_scenario.csv     시나리오별 종합 점수·TOPSIS·순위
  composite_overall.csv/.md     방법별 평균 순위 (전체 / 패턴별)
  rank_by_added_metric.csv/.png 지표 누적 추가에 따른 평균 순위
  timing_table.csv/.md          K별 시간·전체 시간·학습 시간 (패턴 3개 평균 ± 표준편차)
  significance.csv              짝지은 t검정 (서비스 비율)
  fig_service_by_pattern.png    패턴별 서비스 비율 평균 ± 표준편차
  fig_metrics_grid_<패턴>.png    패턴별 지표 9개 × K (오차막대 = 표준편차)
  fig_timing.png                방법별 K당 시간 (로그축)
실행: python3 step5_analyze.py
================================================================
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
OUT = os.path.join("experiment_results", "step5")
AN = os.path.join(OUT, "analysis")
# (지표, 표 이름, 방향 +1=클수록 좋음)
MET = [("Service_Ratio", "서비스 비율(%)", 1), ("PDR", "PDR(%)", 1), ("Total_Received", "총 수신량", 1),
       ("Jain_RSU", "Jain RSU", 1), ("Jain_Vehicle", "Jain 차량", 1), ("RSSI_Mean_dBm", "RSSI(dBm)", 1),
       ("PER", "PER(%)", -1), ("Collisions", "충돌 수", -1), ("Channel_Busy", "채널 점유율(%)", -1)]
TIME = ("Time_s", "계산 시간(s)", -1)
EN = {"GA-연속그룹 (기존 연산)": "Continuous group-GA (old operators)", "Grid top-K": "Grid top-K", "Greedy-교차로": "Greedy-intersection", "Greedy-전체교차로": "Greedy-all junctions",
      "GA-집합 (도로점)": "Set-GA", "GA-연속그룹": "Continuous group-GA", "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "ILP (optimal)"}
COL = {"GA-연속그룹 (기존 연산)": "#f3d27a", "Grid top-K": "#8d8c86", "Greedy-교차로": "#2a6fdb", "Greedy-전체교차로": "#1b998b", "GA-집합 (도로점)": "#eb6834",
       "GA-연속그룹": "#e3a008", "PPO": "#8e44ad", "DQN": "#c0392b", "최적해(ILP)": "#0b0b0b"}
PAT = {"P1": "P1 random", "P2": "P2 downtown", "P3": "P3 arterial"}


def md(df, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n")
        for r in df.itertuples(index=False):
            f.write("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |\n")


def load():
    S = pd.read_csv(os.path.join(OUT, "step5_verify_summary.csv"), encoding="utf-8-sig")
    raw = pd.read_csv(os.path.join(OUT, "step5_verify_raw.csv"))
    raw = raw[raw.Success.astype(str) == "True"]
    T = []
    for p in S.Pattern.unique():
        pl = pd.read_csv(os.path.join(OUT, p, "placements.csv"), encoding="utf-8-sig")
        tm = pd.read_csv(os.path.join(OUT, p, "timing.csv"), encoding="utf-8-sig")
        pl = pl.merge(tm[["Method", "Prep_s", "Train_s"]], on="Method", how="left")
        pl["Pattern"] = p
        T.append(pl)
    T = pd.concat(T)
    # 계산 시간(종합 점수용) = 준비(커버리지 행렬 등) + 그 K 풀이. 학습 시간은 따로 표기.
    T["Time_s"] = T.Prep_s.fillna(0) + T.Time_K_s
    S = S.merge(T[["Pattern", "Method", "K", "Time_s", "Time_K_s", "Prep_s", "Train_s"]], on=["Pattern", "Method", "K"], how="left")
    S["Time_s_mean"] = S.Time_s
    return S, raw, T


def norm_score(block, mets):
    """시나리오 1개(패턴×K)의 방법들: 지표별 min-max 정규화(좋을수록 1) 평균"""
    Z = []
    for m, _, d in mets:
        v = block[f"{m}_mean"].to_numpy(float)
        if m == "Time_s":
            v = np.log10(np.maximum(v, 1e-4))   # 시간은 자릿수 차이가 커서 로그
        rng = v.max() - v.min()
        z = np.full(len(v), 0.5) if rng < 1e-12 else (v - v.min()) / rng
        Z.append(z if d > 0 else 1 - z)
    return np.mean(Z, axis=0)


def topsis(block, mets):
    X = np.column_stack([np.log10(np.maximum(block[f"{m}_mean"].to_numpy(float), 1e-4)) if m == "Time_s"
                         else block[f"{m}_mean"].to_numpy(float) for m, _, _ in mets])
    X = X - X.min(0) + 1e-9                      # RSSI처럼 음수인 지표 대비
    V = X / np.sqrt((X ** 2).sum(0))
    d = np.array([dd for _, _, dd in mets])
    best = np.where(d > 0, V.max(0), V.min(0)); worst = np.where(d > 0, V.min(0), V.max(0))
    sp, sn = np.sqrt(((V - best) ** 2).sum(1)), np.sqrt(((V - worst) ** 2).sum(1))
    return sn / (sp + sn + 1e-12)


def main():
    os.makedirs(AN, exist_ok=True)
    S, raw, T = load()
    methods = [m for m in EN if m in set(S.Method)]
    pats = sorted(S.Pattern.unique())

    # 1) 평균 ± 표준편차 표
    rows = []
    for r in S.sort_values(["Pattern", "K", "Method"]).itertuples():
        d = {"패턴": r.Pattern, "K": r.K, "방법": r.Method, "n": r.n}
        for m, lab, _ in MET:
            mu, sd = getattr(r, f"{m}_mean"), getattr(r, f"{m}_std")
            dec = 0 if m in ("Total_Received", "Collisions") else (3 if m.startswith("Jain") or m == "PER" else 2)
            d[lab] = f"{mu:.{dec}f} ± {sd:.{dec}f}"
        d["계산 시간(s)"] = f"{r.Time_s:.3f}" if pd.notna(r.Time_s) else ""
        rows.append(d)
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(AN, "table_mean_std.csv"), index=False, encoding="utf-8-sig")
    md(tab, os.path.join(AN, "table_mean_std.md"))

    # 2) 종합 점수 (지표 9개 + 계산 시간) — 시나리오마다
    allm = MET + [TIME]
    comp = []
    for (p, K), b in S.groupby(["Pattern", "K"]):
        b = b.reset_index(drop=True)
        sc, tp = norm_score(b, allm), topsis(b, allm)
        sc9 = norm_score(b, MET)
        for i, r in b.iterrows():
            comp.append(dict(Pattern=p, K=K, Method=r.Method, Score_all=sc[i], Score_noTime=sc9[i], TOPSIS=tp[i]))
    C = pd.DataFrame(comp)
    for c in ("Score_all", "Score_noTime", "TOPSIS"):
        C[f"Rank_{c}"] = C.groupby(["Pattern", "K"])[c].rank(ascending=False, method="min")
    C.round(4).to_csv(os.path.join(AN, "composite_by_scenario.csv"), index=False, encoding="utf-8-sig")
    O = C.groupby("Method").agg(Scenarios=("K", "size"), 평균순위_전체지표=("Rank_Score_all", "mean"),
                                평균순위_시간제외=("Rank_Score_noTime", "mean"), 평균순위_TOPSIS=("Rank_TOPSIS", "mean"),
                                종합점수_평균=("Score_all", "mean"), 종합점수_표준편차=("Score_all", "std"))
    for p in pats:
        O[f"평균순위_{p}"] = C[C.Pattern == p].groupby("Method").Rank_Score_all.mean()
    O = O.sort_values("평균순위_전체지표").round(3).reset_index()
    O.to_csv(os.path.join(AN, "composite_overall.csv"), index=False, encoding="utf-8-sig")
    md(O, os.path.join(AN, "composite_overall.md"))
    print("종합 순위 (낮을수록 좋음)\n", O.to_string(index=False))

    # 3) 지표를 하나씩 추가
    add_rows = []
    for i in range(1, len(allm) + 1):
        mets = allm[:i]
        rk = []
        for (p, K), b in S.groupby(["Pattern", "K"]):
            b = b.reset_index(drop=True)
            s = pd.Series(norm_score(b, mets), index=b.Method)
            rk.append(s.rank(ascending=False, method="min"))
        R = pd.concat(rk, axis=1).mean(axis=1)
        add_rows.append(dict(추가한지표="+" + allm[i - 1][1] if i > 1 else allm[0][1], **R.to_dict()))
    A = pd.DataFrame(add_rows).set_index("추가한지표")[methods]
    A.round(2).to_csv(os.path.join(AN, "rank_by_added_metric.csv"), encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(1.1 * len(methods) + 3, 0.45 * len(A) + 1.5))
    im = ax.imshow(A.to_numpy(float), cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks(range(len(methods))); ax.set_xticklabels([EN[m] for m in methods], rotation=30, ha="right", fontsize=8)
    lab_en = ["Service ratio", "+PDR", "+Total received", "+Jain RSU", "+Jain vehicle", "+RSSI", "+PER", "+Collisions",
              "+Channel busy", "+Computation time"]
    ax.set_yticks(range(len(A))); ax.set_yticklabels(lab_en[:len(A)], fontsize=8)
    for i in range(A.shape[0]):
        for j in range(A.shape[1]):
            ax.text(j, i, f"{A.iat[i, j]:.1f}", ha="center", va="center", fontsize=7.5)
    ax.set_title("Mean rank over all scenarios as metrics are added one by one (lower = better)", loc="left", fontsize=10)
    plt.colorbar(im, ax=ax, fraction=0.03); plt.tight_layout()
    plt.savefig(os.path.join(AN, "rank_by_added_metric.png"), dpi=150); plt.close()

    # 4) 시간 표 (패턴 평균 ± 표준편차)
    tr = []
    for m in methods:
        t = T[T.Method == m]
        if t.empty:
            continue
        d = {"방법": m}
        for K in sorted(t.K.unique()):
            v = t[t.K == K].Time_K_s
            d[f"K={K} (s)"] = f"{v.mean():.4f} ± {v.std(ddof=1) if len(v) > 1 else 0:.4f}"
        pp = t.groupby("Pattern").agg(prep=("Prep_s", "first"), train=("Train_s", "first"), sk=("Time_K_s", "sum"))
        d["준비(s)"] = f"{pp.prep.mean():.1f} ± {pp.prep.std(ddof=1) if len(pp) > 1 else 0:.1f}"
        d["학습(s)"] = f"{pp.train.mean():.1f} ± {pp.train.std(ddof=1) if len(pp) > 1 else 0:.1f}"
        tot = pp.prep + pp.train + pp.sk
        d["전체(s)"] = f"{tot.mean():.1f} ± {tot.std(ddof=1) if len(pp) > 1 else 0:.1f}"
        d["패턴 수"] = len(pp)
        tr.append(d)
    TT = pd.DataFrame(tr)
    TT.to_csv(os.path.join(AN, "timing_table.csv"), index=False, encoding="utf-8-sig")
    md(TT, os.path.join(AN, "timing_table.md"))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for m in methods:
        t = T[T.Method == m].groupby("K").Time_K_s.agg(["mean", "std"])
        ax.errorbar(t.index, t["mean"], yerr=t["std"].fillna(0), marker="o", ms=3.5, lw=1.5, capsize=2, color=COL[m], label=EN[m])
    ax.set_yscale("log"); ax.set_xlabel("K"); ax.set_ylabel("Time to solve one K (s, log)")
    ax.set_title("Computation time per K (mean ± std over traffic patterns; RL training excluded)", loc="left", fontsize=10)
    ax.grid(color="#e6e5e0"); ax.legend(frameon=False, fontsize=7.5, ncol=2); plt.tight_layout()
    plt.savefig(os.path.join(AN, "fig_timing.png"), dpi=150); plt.close()

    # 5) 유의성: 시나리오별 종합 1위 vs 나머지, 서비스 비율, 같은 seed끼리 짝지음
    try:
        from scipy import stats
    except ImportError:
        stats = None
    sig = []
    if stats is not None:
        for (p, K), c in C.groupby(["Pattern", "K"]):
            best = c.sort_values("Score_all", ascending=False).Method.iloc[0]
            rb = raw[(raw.Pattern == p) & (raw.K == K)]

            def series(m):
                key = S[(S.Pattern == p) & (S.K == K) & (S.Method == m)].Key.iloc[0]
                return rb[rb.Key == key].set_index("Seed").Service_Ratio

            sb = series(best)
            for m in c.Method:
                if m == best:
                    continue
                so = series(m)
                idx = sb.index.intersection(so.index)
                diff = (sb[idx] - so[idx]).to_numpy()
                if len(idx) < 2 or np.allclose(diff, 0):
                    pv = np.nan if len(idx) < 2 else 1.0
                else:
                    pv = stats.ttest_rel(sb[idx], so[idx]).pvalue
                sig.append(dict(Pattern=p, K=K, Best=best, Other=m, n=len(idx), Diff_mean=diff.mean() if len(idx) else np.nan,
                                p_value=pv, Significant_005=bool(pv < 0.05) if pv == pv else False))
        Fr = C.pivot_table(index=["Pattern", "K"], columns="Method", values="Score_all").dropna(axis=1)
        if Fr.shape[1] >= 3 and Fr.shape[0] >= 2:
            fr = stats.friedmanchisquare(*[Fr[c] for c in Fr.columns])
            print(f"\nFriedman 검정 (종합 점수, 시나리오 {Fr.shape[0]}개 × 방법 {Fr.shape[1]}개): χ²={fr.statistic:.2f}, p={fr.pvalue:.4g}")
    pd.DataFrame(sig).round(4).to_csv(os.path.join(AN, "significance.csv"), index=False, encoding="utf-8-sig")

    # 6) 그래프: 패턴별 서비스 비율
    fig, axes = plt.subplots(1, len(pats), figsize=(5.2 * len(pats), 4.2), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, p in zip(axes, pats):
        for m in methods:
            s = S[(S.Pattern == p) & (S.Method == m)].sort_values("K")
            ax.errorbar(s.K + (methods.index(m) - len(methods) / 2) * 0.05, s.Service_Ratio_mean, yerr=s.Service_Ratio_std,
                        marker="o", ms=3, lw=1.4, capsize=2, color=COL[m], label=EN[m])
        n = int(S[S.Pattern == p].n.min())
        ax.set_title(f"{PAT.get(p, p)}  (n={n} runs each)", loc="left", fontsize=10)
        ax.set_xlabel("K"); ax.grid(color="#e6e5e0")
    axes[0].set_ylabel("Service ratio (%)  mean ± std"); axes[0].legend(frameon=False, fontsize=7.5)
    plt.tight_layout(); plt.savefig(os.path.join(AN, "fig_service_by_pattern.png"), dpi=150); plt.close()
    for p in pats:
        fig, axs = plt.subplots(3, 3, figsize=(15, 11))
        for ax, (m_key, _, _) in zip(axs.ravel(), MET):
            for m in methods:
                s = S[(S.Pattern == p) & (S.Method == m)].sort_values("K")
                ax.errorbar(s.K, s[f"{m_key}_mean"], yerr=s[f"{m_key}_std"], marker="o", ms=3, lw=1.3, capsize=2,
                            color=COL[m], label=EN[m])
            ax.set_title(m_key, loc="left", fontsize=10); ax.grid(color="#e6e5e0"); ax.set_xlabel("K")
        axs[0, 0].legend(frameon=False, fontsize=7)
        fig.suptitle(f"{PAT.get(p, p)}: all metrics (mean ± std)", x=0.01, ha="left")
        plt.tight_layout(); plt.savefig(os.path.join(AN, f"fig_metrics_grid_{p}.png"), dpi=130); plt.close()
    print(f"\n완료 → {AN}")


if __name__ == "__main__":
    main()
