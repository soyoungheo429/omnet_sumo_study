import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans

# 1. 수집한 데이터 로드
csv_file = "vehicle_snapshots.csv"
df = pd.read_csv(csv_file)

# 2. 클러스터링 (K개 RSU 설치 시 위치 선정)
K = 5 # 설치할 RSU 개수
X = df[['x', 'y']].values
kmeans = KMeans(n_clusters=K, n_init=10, random_state=42)
kmeans.fit(X)
centroids = kmeans.cluster_centers_

# 3. 시각화 (히트맵 + 스티커)
plt.figure(figsize=(10, 8))

# 차량 밀도 히트맵 (Reds 색상맵 사용)
sns.kdeplot(x=df['x'], y=df['y'], fill=True, cmap='Reds', thresh=0.05, alpha=0.6, label='Vehicle Density')

# RSU 배치 위치(스티커) 표시
plt.scatter(centroids[:, 0], centroids[:, 1], s=250, color='blue', marker='X', edgecolors='white', linewidth=1.5, label='Optimal RSU Placement')

plt.title(f"Vehicle Traffic Density and Optimal RSU Placement (K={K})", fontsize=15)
plt.xlabel("X Coordinate (m)", fontsize=12)
plt.ylabel("Y Coordinate (m)", fontsize=12)
plt.legend(loc='upper right')
plt.grid(True, linestyle='--', alpha=0.3)

# 결과 저장
plt.savefig("rsu_placement_result.png", dpi=300)
print("✔ 시각화 완료: 'rsu_placement_result.png' 파일이 생성되었습니다.")
plt.show()

# 4. 좌표 데이터를 CSV로 별도 저장
coord_df = pd.DataFrame(centroids, columns=['x', 'y'])
coord_df.to_csv("optimal_rsu_coords.csv", index=False)
print("✔ 최적 좌표 저장 완료: 'optimal_rsu_coords.csv'")
