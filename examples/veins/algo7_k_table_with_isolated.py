"""
algo7_k_table_with_isolated.py
================================================================
K별 메인 결과 표에 "그 K에서 새로 추가된 RSU(Rank=K)의 단독 PDR"과
"Rank 1~K까지 단독 PDR의 누적 합"을 추가하는 스크립트
================================================================

의미:
  - "추가되는 RSU 단독 PDR": K번째 스텝에서 새로 배치되는 RSU(=Rank K)가
    혼자 있을 때의 PDR
  - "1~K 단독 PDR 합": Rank 1부터 Rank K까지, 각각 혼자 있었을 때의 PDR을
    그냥 더한 값 (RSU 간 상호작용이 전혀 없다고 가정했을 때의 기대치)
  - 이 값과 실제 "평균 PDR(%)"(K개를 동시에 배치했을 때 실측값)을 비교하면,
    RSU들을 같이 배치했을 때 서로 도움이 되는지(실측 > 합) 방해가 되는지
    (실측 < 합) 확인할 수 있다
"""

import pandas as pd

K_TABLE_CSV = "algo7_k_pdr_received_table.csv"
ISOLATED_TREND_CSV = "algo7_isolated_rsu_trend.csv"
OUT_CSV = "algo7_k_table_with_isolated.csv"

k_df = pd.read_csv(K_TABLE_CSV)
iso_df = pd.read_csv(ISOLATED_TREND_CSV).sort_values("Rank").reset_index(drop=True)

# Rank=K인 후보의 단독 PDR ("이번에 새로 추가된 RSU 혼자만의 PDR")
iso_pdr_by_rank = dict(zip(iso_df["Rank"], iso_df["PDR_Mean"]))

k_col = "K (RSU 대수)" if "K (RSU 대수)" in k_df.columns else "K"

k_df["추가되는 RSU 단독 PDR"] = k_df[k_col].map(iso_pdr_by_rank)

# Rank 1~K까지 단독 PDR 누적 합
iso_df_sorted = iso_df.sort_values("Rank")
cum_sum_by_rank = iso_df_sorted.set_index("Rank")["PDR_Mean"].cumsum()
k_df["1~K 단독 PDR 합"] = k_df[k_col].map(cum_sum_by_rank)

k_df = k_df.round(2)
k_df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

print(k_df.to_string(index=False))
print(f"\n✔ 저장 완료: '{OUT_CSV}'")
