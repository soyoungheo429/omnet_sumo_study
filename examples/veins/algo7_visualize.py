'''
import pandas as pd
import matplotlib.pyplot as plt

# 1. 데이터 로드
csv_file = "vehicle_snapshots.csv"
df = pd.read_csv(csv_file)

# 2. 산점도 시각화
plt.figure(figsize=(12, 10))

# 5,000개의 점을 투명도를 주어 밀집도를 파악하기 쉽게 시각화
# alpha=0.1 : 점이 많이 겹칠수록 진하게 보임 (밀도 시각화)
plt.scatter(df['x'], df['y'], s=1, alpha=0.1, color='blue', label='Vehicle Positions')

plt.title("Vehicle Traffic Distribution (Snapshot Analysis)", fontsize=15)
plt.xlabel("X Coordinate (m)")
plt.ylabel("Y Coordinate (m)")
plt.legend(loc='upper right')
plt.grid(True, linestyle='--', alpha=0.3)

# 파일로 저장
plt.savefig("vehicle_scatter_plot.png", dpi=300)
print("✔ 시각화 완료: 'vehicle_scatter_plot.png' 파일이 생성되었습니다.")
plt.show()
'''

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

# 1. 데이터 로드
csv_file = "vehicle_snapshots.csv"
df = pd.read_csv(csv_file)

# 2. 2D 히스토그램(히트맵) 시각화
# 점이 너무 많이 겹쳐 alpha 조정만으로는 도로별 밀도 차이가 안 보이므로,
# 칸(bin)별 포인트 개수를 세서 로그 스케일 컬러로 표현 -> 조금 붐비는 곳과
# 아주 붐비는 곳의 차이가 색으로 뚜렷하게 드러남
plt.figure(figsize=(12, 10))

h = plt.hist2d(df['x'], df['y'], bins=400, cmap='inferno', norm=LogNorm())
plt.colorbar(h[3], label='Vehicle Snapshot Count (log scale)')

plt.title("Vehicle Traffic Density Heatmap (Snapshot Analysis)", fontsize=15)
plt.xlabel("X Coordinate (m)")
plt.ylabel("Y Coordinate (m)")
plt.gca().set_aspect('equal')

# 파일로 저장
plt.savefig("vehicle_scatter_plot.png", dpi=300)
print("✔ 시각화 완료: 'vehicle_scatter_plot.png' 파일이 생성되었습니다.")
plt.show()
