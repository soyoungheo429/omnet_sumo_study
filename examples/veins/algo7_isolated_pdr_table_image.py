"""
algo7_isolated_pdr_table_image.py
================================================================
27개 후보 단독(K=1) PDR 결과를 발표용 표 이미지로 만드는 스크립트
(Rank 8 행만 강조 색으로 표시)
================================================================
"""

import pandas as pd
import matplotlib.pyplot as plt

TREND_CSV = "algo7_isolated_rsu_trend.csv"
OUT_PNG = "algo7_isolated_pdr_table.png"

df = pd.read_csv(TREND_CSV).sort_values("Rank").reset_index(drop=True)

display_df = df[["Rank", "PDR_Mean", "PDR_Std", "Received_Mean", "Received_Std", "N"]].copy()
display_df.columns = ["Rank", "평균 PDR(%)", "PDR 표준편차", "평균 수신 패킷 수", "수신량 표준편차", "반복 횟수"]

# 보기 좋게 소수점 정리
display_df["평균 PDR(%)"] = display_df["평균 PDR(%)"].map(lambda v: f"{v:.2f}")
display_df["PDR 표준편차"] = display_df["PDR 표준편차"].map(lambda v: f"{v:.2f}")
display_df["평균 수신 패킷 수"] = display_df["평균 수신 패킷 수"].map(lambda v: f"{v:.1f}")
display_df["수신량 표준편차"] = display_df["수신량 표준편차"].map(lambda v: f"{v:.2f}")

fig_h = 0.42 * len(display_df) + 1.2
fig, ax = plt.subplots(figsize=(11, fig_h))
ax.axis("off")

table = ax.table(cellText=display_df.values, colLabels=display_df.columns,
                  loc="center", cellLoc="center")
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1, 1.55)

for j in range(len(display_df.columns)):
    cell = table[0, j]
    cell.set_facecolor("#2b5d8c")
    cell.set_text_props(color="white", fontweight="bold")

rank8_row_idx = display_df.index[df["Rank"] == 8][0]
for j in range(len(display_df.columns)):
    cell = table[rank8_row_idx + 1, j]
    cell.set_facecolor("#f7cfa0")
    cell.set_text_props(fontweight="bold")

ax.set_title("후보 RSU 27개 단독(K=1) PDR / 수신 패킷 비교 (Rank 8 강조)",
              fontsize=14, fontweight="bold", pad=14)

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
print(f"✔ 저장 완료: '{OUT_PNG}'")
