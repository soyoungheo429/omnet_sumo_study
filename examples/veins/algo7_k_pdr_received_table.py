"""
algo7_k_pdr_received_table.py
================================================================
K=1~27 메인 결과에 "평균 수신 패킷 총량"을 같이 정리해서
전체 표(CSV)와 이중축 그래프(PDR 막대 + 수신량 선)로 만드는 스크립트
================================================================
"""

import pandas as pd
import matplotlib.pyplot as plt

RAW_CSV = "algo7_k_vs_pdr_multirun_raw.csv"
OUT_TABLE_CSV = "algo7_k_pdr_received_table.csv"
OUT_PLOT_PNG = "algo7_k_pdr_received_combo.png"

df = pd.read_csv(RAW_CSV)

summary = df.groupby("K").agg(
    PDR_Mean=("PDR(%)", "mean"),
    PDR_Std=("PDR(%)", "std"),
    Received_Mean=("Actual_Received", "mean"),
    Received_Std=("Actual_Received", "std"),
    Generated_Mean=("Total_Generated", "mean"),
    N=("PDR(%)", "count"),
).reset_index().round(2)
summary["PDR_Std"] = summary["PDR_Std"].fillna(0.0)
summary["Received_Std"] = summary["Received_Std"].fillna(0.0)

summary.to_csv(OUT_TABLE_CSV, index=False, encoding="utf-8-sig")

print("=" * 80)
print(" K별 평균 PDR + 평균 수신 패킷 총량 (전체 표)")
print("=" * 80)
display_df = summary.rename(columns={
    "K": "K (RSU 대수)", "PDR_Mean": "평균 PDR(%)", "PDR_Std": "PDR 표준편차",
    "Received_Mean": "평균 수신 패킷 수", "Received_Std": "수신량 표준편차",
    "Generated_Mean": "평균 발신 패킷 수", "N": "반복 횟수",
})
print(display_df.to_string(index=False))
print("=" * 80)
print(f"\n✔ 전체 표가 '{OUT_TABLE_CSV}' 파일로 저장되었습니다.")

# 이중축 그래프: 막대(PDR, 왼쪽 축) + 선(수신 패킷 총량, 오른쪽 축)
plt.rcParams['axes.unicode_minus'] = False
fig, ax1 = plt.subplots(figsize=(14, 7))

ax1.bar(summary["K"], summary["PDR_Mean"], yerr=summary["PDR_Std"], capsize=3,
        color='cornflowerblue', alpha=0.85, label='Mean PDR (%)')
ax1.set_xlabel("K (Number of Deployed RSUs)", fontsize=13)
ax1.set_ylabel("Mean PDR (%)", fontsize=13, color='#2b5d8c')
ax1.set_xticks(summary["K"])
ax1.tick_params(axis='y', labelcolor='#2b5d8c')
ax1.grid(True, axis='y', linestyle='--', alpha=0.4)

ax2 = ax1.twinx()
ax2.plot(summary["K"], summary["Received_Mean"], 'o-', color='firebrick', linewidth=2,
         markersize=6, label='Mean Received Packets')
ax2.set_ylabel("Mean Received Packet Count", fontsize=13, color='firebrick')
ax2.tick_params(axis='y', labelcolor='firebrick')

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

plt.title("PDR and Received Packet Volume by K", fontsize=15, pad=16)
plt.tight_layout()
plt.savefig(OUT_PLOT_PNG, dpi=300)
print(f"✔ 그래프가 '{OUT_PLOT_PNG}' 파일로 저장되었습니다.")
