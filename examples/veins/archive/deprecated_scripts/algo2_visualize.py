import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# 데이터 파일 이름
CSV_FILE = "bruteforce_grid_results.csv"

# 1. 데이터 불러오기 및 에러(-1.0) 데이터 필터링
try:
    df = pd.read_csv(CSV_FILE)
except FileNotFoundError:
    print(f"[{CSV_FILE}] 파일이 없습니다. 시뮬레이션을 먼저 끝까지 돌려주세요!")
    exit()

df_valid = df[df["PDR"] >= 0].copy()

if df_valid.empty:
    print("정상적으로 PDR이 기록된 데이터가 없습니다.")
    exit()

# ==========================================
# 1. 표(Table) 시각화: 상위 10개 최적 위치 출력
# ==========================================
top10_df = df_valid.nlargest(10, 'PDR').reset_index(drop=True)

print("\n" + "="*50)
print(" 🏆 [표 1] 최적 RSU 위치 Top 10 (PDR 기준)")
print("="*50)
# 판다스를 이용해 콘솔에 예쁜 표 형태로 출력
print(top10_df[['ID', 'Rel_X', 'Rel_Y', 'PDR']].to_string(index=False))
print("="*50 + "\n")

# Top 10 데이터를 CSV로 별도 저장 (논문 첨부용)
top10_df.to_csv("top10_rsu_results.csv", index=False)


# ==========================================
# 2. 그래프(Graph) 1: Top 10 성능 비교 바 차트 (Bar Chart)
# ==========================================
plt.figure(figsize=(10, 6))
# Seaborn을 활용하여 PDR 수치에 따라 색상이 그라데이션 되도록 설정
sns.barplot(x='ID', y='PDR', data=top10_df, palette='viridis')

plt.title("Top 10 RSU Locations by Packet Delivery Ratio (PDR)", fontsize=14, pad=15)
plt.xlabel("Grid ID", fontsize=12)
plt.ylabel("PDR (%)", fontsize=12)
plt.ylim(0, max(top10_df['PDR']) * 1.2) # Y축 여유 공간 확보

# 막대 그래프 위에 정확한 PDR 수치 표시
for index, value in enumerate(top10_df['PDR']):
    plt.text(index, value + 0.5, f'{value:.2f}%', ha='center', fontsize=10, fontweight='bold')

plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig("graph_top10_bar.png", dpi=300)
print("=> 'graph_top10_bar.png' (바 차트) 저장 완료!")


# ==========================================
# 3. 그래프(Graph) 2: 2D Grid 형태의 표 & 히트맵 (Heatmap)
# ==========================================
# 엑셀의 '피벗 테이블(Pivot Table)'처럼 데이터를 X, Y 좌표 기준의 2차원 표로 변환
grid_pivot = df_valid.pivot(index='Rel_Y', columns='Rel_X', values='PDR')

# 지도처럼 Y축 값이 위로 갈수록 커지도록 인덱스 정렬 (아래에서 위로)
grid_pivot = grid_pivot.sort_index(ascending=False)

plt.figure(figsize=(12, 10))
# annot=False: 칸이 너무 많으므로 숫자 표시는 끔 (필요시 True로 변경 가능)
ax = sns.heatmap(grid_pivot, cmap='RdYlGn', annot=False, 
                 cbar_kws={'label': 'Packet Delivery Ratio (%)'}, 
                 linewidths=0.5, linecolor='lightgray')

plt.title("Global Search PDR Grid (150m Resolution)", fontsize=16, pad=20)
plt.xlabel("X Coordinate (m)", fontsize=12)
plt.ylabel("Y Coordinate (m)", fontsize=12)

# X, Y축 라벨 보기 좋게 회전
plt.xticks(rotation=45)
plt.yticks(rotation=0)

plt.tight_layout()
plt.savefig("graph_grid_table_heatmap.png", dpi=300)
print("=> 'graph_grid_table_heatmap.png' (그리드 표 히트맵) 저장 완료!")
print("\n모든 시각화가 완료되었습니다. 논문 작성에 바로 활용하세요! 😊")
