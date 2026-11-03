#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step4_k_selection_plot.py — 실측(step4_verify_summary.csv)으로 'K를 몇 대로?' 그림
   왼쪽: K별 서비스 비율 (기존 algo1/algo7 vs 수정 Greedy) + 목표선 60/70/80%
   오른쪽: 수정 Greedy에서 RSU 1대 추가할 때 늘어나는 서비스 비율(한계이득)"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
OUT = os.path.join("experiment_results", "step4")
S = pd.read_csv(os.path.join(OUT, "step4_verify_summary.csv"), encoding="utf-8-sig")
g = S[S.Method == "Greedy-전체교차로 (algo7 수정)"].sort_values("K")
a1 = S[S.Method == "algo1 (기존)"].sort_values("K")
a7 = S[S.Method == "algo7 (기존)"].sort_values("K")
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
ax = axes[0]
ax.plot(a1.K, a1.Service_Ratio, "o--", color="#b9b8b2", label="algo1 (old)")
ax.plot(a7.K, a7.Service_Ratio, "o--", color="#8d8c86", label="algo7 (old)")
ax.plot(g.K, g.Service_Ratio, "o-", color="#2a6fdb", lw=2.2, label="Greedy (fixed)")
for t in (60, 70, 80):
    k = int(g[g.Service_Ratio >= t].K.min()) if (g.Service_Ratio >= t).any() else None
    ax.axhline(t, color="#e6e5e0", lw=1, zorder=0)
    if k:
        ax.annotate(f"{t}% → K={k}", (k, t), xytext=(6, -14), textcoords="offset points", fontsize=9, color="#2a6fdb")
ax.set_xlabel("K (number of RSUs)"); ax.set_ylabel("Measured service ratio (%)")
ax.set_title("Service ratio in OMNeT++/Veins", loc="left", fontsize=11); ax.set_xticks(range(1, 11))
ax.grid(color="#e6e5e0"); ax.legend(frameon=False, fontsize=9, loc="lower right")
ax = axes[1]
gain = g.Service_Ratio.diff().fillna(g.Service_Ratio.iloc[0])
bars = ax.bar(g.K, gain, color=["#2a6fdb" if k <= 3 else "#9cc3f0" for k in g.K])
for b, v in zip(bars, gain):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.4, f"{v:.1f}", ha="center", fontsize=8)
ax.set_xlabel("k-th RSU added"); ax.set_ylabel("Added service ratio (%p)")
ax.set_title("Gain per added RSU (fixed Greedy): drops after K=3", loc="left", fontsize=11)
ax.set_xticks(range(1, 11)); ax.grid(color="#e6e5e0", axis="y")
plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_k_selection.png"), dpi=150)
print(g[["K", "Service_Ratio"]].assign(Gain=gain.round(1)).to_string(index=False))
