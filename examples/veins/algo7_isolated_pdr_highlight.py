"""
algo7_isolated_pdr_highlight.py
================================================================
단독(K=1) PDR 비교 그래프에서 Rank 8만 강조 색으로 표시하는 발표용 버전
================================================================
"""

import pandas as pd
import matplotlib.pyplot as plt

TREND_CSV = "algo7_isolated_rsu_trend.csv"
OUT_PNG = "algo7_isolated_pdr_highlight.png"

df = pd.read_csv(TREND_CSV).sort_values("Rank").reset_index(drop=True)

colors = ["#d9720c" if r == 8 else "#3b6ea5" for r in df["Rank"]]

plt.rcParams['axes.unicode_minus'] = False
fig, ax = plt.subplots(figsize=(14, 7))

ax.bar(df["Rank"], df["PDR_Mean"], yerr=df["PDR_Std"], capsize=3,
       color=colors, edgecolor="white", linewidth=0.8)

for _, row in df.iterrows():
    if row["Rank"] == 8:
        ax.annotate(f"Rank 8\n{row['PDR_Mean']:.2f}%",
                    xy=(row["Rank"], row["PDR_Mean"]),
                    xytext=(row["Rank"] + 1.5, row["PDR_Mean"] + 0.6),
                    fontsize=12, fontweight="bold", color="#d9720c",
                    arrowprops=dict(arrowstyle="->", color="#d9720c", lw=1.5))

ax.set_xlabel("Candidate Rank (tested alone as K=1)", fontsize=13)
ax.set_ylabel("Isolated PDR (%)", fontsize=13)
ax.set_title("Isolated PDR by RSU Candidate — Rank 8 Highlighted", fontsize=15, pad=16)
ax.set_xticks(df["Rank"])
ax.grid(True, axis='y', linestyle='--', alpha=0.4)

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300)
print(f"✔ 저장 완료: '{OUT_PNG}'")
