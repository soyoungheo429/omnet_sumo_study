#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_report_figs.py   (랩미팅/논문용 표·지도·그래프 생성, 시뮬레이션 0회)
================================================================
입력: experiment_results/step4/step4_verify_summary.csv (실측), step4_placements.csv (좌표)
출력 (experiment_results/step4/report/):
  tables_by_method.md / .csv     방법별 K=1~10 표 (서비스비율, PDR, 총수신량, Jain RSU/차량, RSSI, PER, 충돌, 채널점유율)
  map_<방법>.png                 방법별 K=1~10 배치 지도 10칸 (번호 = 추가 순서, 파랑 = 덮인 차량 위치)
  map_compare_K3_5_10.png        방법 × K(3,5,10) 비교 지도
  metric_bars_K5_K10.png         K=5, K=10에서 방법별 지표 막대그래프
실행:  python3 step4_report_figs.py
================================================================
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
from rsu_lib.surrogate import Surrogate  # noqa: E402

OUT = os.path.join("experiment_results", "step4")
REP = os.path.join(OUT, "report")
os.makedirs(REP, exist_ok=True)
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
METHODS = [  # (표/파일 키, CSV 방법명, 짧은 영어 이름, 색)
    ("algo1_old", "algo1 (기존)", "algo1 (old)", "#b9b8b2"),
    ("algo7_old", "algo7 (기존)", "algo7 (old)", "#8d8c86"),
    ("algo1_fixed", "Greedy-교차로 (algo1 수정)", "algo1' Greedy (111 junctions)", "#2a6fdb"),
    ("algo7_fixed", "Greedy-전체교차로 (algo7 수정)", "algo7' Greedy (195 junctions)", "#1b998b"),
    ("ga", "GA-집합 (도로점)", "Set-GA (road points)", "#eb6834"),
    ("ppo", "PPO", "PPO", "#8e44ad"),
    ("dqn", "DQN", "DQN", "#c0392b"),
    ("ilp", "최적해(ILP)", "Optimal (ILP)", INK),
]
KOR = {"algo1 (기존)": "algo1 (기존)", "algo7 (기존)": "algo7 (기존)", "Greedy-교차로 (algo1 수정)": "algo1′ (교차로 111곳 Greedy)",
       "Greedy-전체교차로 (algo7 수정)": "algo7′ (전체 교차로 195곳 Greedy)", "GA-집합 (도로점)": "집합 GA", "PPO": "PPO", "DQN": "DQN",
       "최적해(ILP)": "최적해(ILP)"}
COLS = [("Service_Ratio", "서비스 비율(%)", 1), ("PDR", "PDR(%)", 2), ("Total_Received", "총 수신량", 0),
        ("Jain_RSU", "Jain RSU", 2), ("Jain_Vehicle", "Jain 차량", 2), ("RSSI_Mean_dBm", "RSSI(dBm)", 1),
        ("PER", "PER(%)", 3), ("Collisions", "충돌 수", 1), ("Channel_Busy", "채널 점유율(%)", 3)]


def extra_old_rows():
    """기존 algo1/algo7 K=6~10 중 에코 수정 후 실측(_oldfill)이 있으면 추가"""
    p = os.path.join(OUT, "step4_verify_summary_oldfill.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    d = pd.read_csv(p, encoding="utf-8-sig")
    return d[d.Method.isin(["algo1 (기존)", "algo7 (기존)"]) & (d.K >= 6) & d.Pred_Cover.notna()]


def tables(S):
    lines, allrows = [], []
    for key, m, en, _ in METHODS:
        d = S[S.Method == m].set_index("K").reindex(range(1, 11))
        lines.append(f"\n### {KOR[m]}\n")
        lines.append("| K | " + " | ".join(c[1] for c in COLS) + " |")
        lines.append("|---|" + "---|" * len(COLS))
        for K, r in d.iterrows():
            vals = []
            for c, _, nd in COLS:
                v = r.get(c)
                vals.append("-" if pd.isna(v) else (f"{v:,.0f}" if nd == 0 else f"{v:.{nd}f}"))
            lines.append(f"| {K} | " + " | ".join(vals) + " |")
            allrows.append(dict(방법=KOR[m], K=K, **{lab: r.get(c) for c, lab, _ in COLS}))
    note = ("\n※ 실측(OMNeT++/Veins). 수정 알고리즘 6종은 2회 평균, 기존 algo1/algo7 K≤5·8·10은 step2(5회 평균), "
            "기존 K=6~10의 나머지는 에코 수정 후 측정 또는 '-'(미측정).\n")
    with open(os.path.join(REP, "tables_by_method.md"), "w", encoding="utf-8") as f:
        f.write("# 방법별 K=1~10 실측 지표\n" + note + "\n".join(lines) + "\n")
    pd.DataFrame(allrows).to_csv(os.path.join(REP, "tables_by_method.csv"), index=False, encoding="utf-8-sig")


def draw_map(ax, S, coords, title, color, bg):
    cov = np.zeros(len(S.pts), bool)
    for p in coords:
        cov |= S.covered(tuple(p))
    for P in bg:
        ax.fill(P[:, 0], P[:, 1], color="#ecebe6", lw=0, zorder=0)
    ax.scatter(S.pts[~cov, 0], S.pts[~cov, 1], s=1.2, color="#c9c8c2", zorder=1)
    ax.scatter(S.pts[cov, 0], S.pts[cov, 1], s=1.2, color="#8fb8ec", zorder=2)
    c = np.array(coords)
    ax.scatter(c[:, 0], c[:, 1], s=46, marker="X", color=color, edgecolor=INK, lw=0.6, zorder=5)
    for i, p in enumerate(c, 1):
        ax.annotate(str(i), p, xytext=(3, 3), textcoords="offset points", fontsize=7, zorder=6)
    ax.set_title(title, fontsize=8.5, loc="left")
    ax.set_xlim(S.pts[:, 0].min() - 120, S.pts[:, 0].max() + 120)
    ax.set_ylim(S.pts[:, 1].max() + 120, S.pts[:, 1].min() - 120)   # 북쪽이 위
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    return 100 * cov.mean()


def maps(S, P, meas):
    bg = S.polys
    for key, m, en, col in METHODS:
        if m in ("PPO", "DQN", "최적해(ILP)"):
            continue
        fig, axes = plt.subplots(2, 5, figsize=(19, 7.2))
        for K, ax in zip(range(1, 11), axes.ravel()):
            r = P[(P.Method == m) & (P.K == K)]
            if r.empty:
                ax.axis("off"); continue
            mv = meas.get((m, K))
            t = f"K={K}" + (f"  measured {mv:.1f}%" if mv is not None and not np.isnan(mv) else "  (not measured)")
            draw_map(ax, S, json.loads(r.Coords.iloc[0]), t, col, bg)
        fig.suptitle(f"{en}: RSU placements K=1–10 (X = RSU, number = order added, blue = vehicle positions covered)",
                     x=0.01, ha="left", fontsize=11)
        plt.tight_layout(); plt.savefig(os.path.join(REP, f"map_{key}.png"), dpi=130); plt.close()
    sel = [x for x in METHODS if x[1] in ("algo1 (기존)", "algo7 (기존)", "Greedy-전체교차로 (algo7 수정)", "GA-집합 (도로점)")]
    fig, axes = plt.subplots(len(sel), 3, figsize=(13, 3.6 * len(sel)))
    for i, (key, m, en, col) in enumerate(sel):
        for j, K in enumerate((3, 5, 10)):
            r = P[(P.Method == m) & (P.K == K)]
            mv = meas.get((m, K))
            t = f"{en}  K={K}" + (f"  {mv:.1f}%" if mv is not None and not np.isnan(mv) else "")
            draw_map(axes[i, j], S, json.loads(r.Coords.iloc[0]), t, col, bg)
    plt.tight_layout(); plt.savefig(os.path.join(REP, "map_compare_K3_5_10.png"), dpi=130); plt.close()


def bars(S):
    show = [("Service_Ratio", "Service ratio (%)"), ("PDR", "PDR (%)"), ("Total_Received", "Total received"),
            ("Jain_RSU", "Jain (RSU)"), ("Jain_Vehicle", "Jain (vehicle)"), ("RSSI_Mean_dBm", "Mean RSSI (dBm)")]
    fig, axes = plt.subplots(2, 6, figsize=(22, 7.5))
    for row, K in enumerate((5, 10)):
        d = S[S.K == K]
        names, cols = [], []
        for key, m, en, col in METHODS:
            if (d.Method == m).any():
                names.append(m); cols.append(col)
        for ax, (c, lab) in zip(axes[row], show):
            vals = [float(d[d.Method == m][c].iloc[0]) for m in names]
            ax.barh(range(len(names)), vals, color=cols)
            ax.set_yticks(range(len(names)))
            ax.set_yticklabels([dict((x[1], x[2]) for x in METHODS)[m] for m in names], fontsize=8)
            ax.invert_yaxis(); ax.grid(color=GRID, axis="x"); ax.set_title(f"K={K}: {lab}", loc="left", fontsize=10)
            if c == "RSSI_Mean_dBm":
                ax.set_xlim(min(vals) - 1, max(vals) + 0.5)
            for i, v in enumerate(vals):
                ax.text(v, i, f" {v:,.0f}" if c == "Total_Received" else f" {v:.2f}" if "Jain" in c else f" {v:.1f}",
                        va="center", fontsize=7)
    plt.tight_layout(); plt.savefig(os.path.join(REP, "metric_bars_K5_K10.png"), dpi=130); plt.close()


def main():
    S = pd.read_csv(os.path.join(OUT, "step4_verify_summary.csv"), encoding="utf-8-sig")
    ex = extra_old_rows()
    if len(ex):
        S = pd.concat([S[~(S.Method.isin(ex.Method.unique()) & S.K.isin(ex.K.unique()) &
                           S.set_index(["Method", "K"]).index.isin(ex.set_index(["Method", "K"]).index))], ex])
    P = pd.read_csv(os.path.join(OUT, "step4_placements.csv"), encoding="utf-8-sig")
    meas = {(r.Method, int(r.K)): r.Service_Ratio for r in S.itertuples()}
    tables(S)
    sur = Surrogate("erlangen.poly.xml", "vehicle_snapshots_2s.csv")
    maps(sur, P, meas)
    bars(S)
    print("저장:", REP, sorted(os.listdir(REP)))


if __name__ == "__main__":
    main()
