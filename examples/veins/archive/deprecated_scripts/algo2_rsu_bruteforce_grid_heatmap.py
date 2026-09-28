import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil

# --- 설정값 ---
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "grid_bruteforce_throughput_results.csv"
SIM_TIME = 200

# 에를랑겐 맵 크기 및 탐색 해상도 (Grid Size)
WIDTH = 2606.46
HEIGHT = 3009.73
GRID_SIZE = 150.0  # 75.0m 로 변경 시 더 촘촘하게 탐색

# 1. Grid 정중앙 좌표 자동 생성 함수
def generate_grid_centers(width, height, step):
    candidates = []
    num_x = int(width // step)
    num_y = int(height // step)
    
    cand_id = 0
    for i in range(num_x):
        for j in range(num_y):
            # 각 격자의 정중앙 좌표 계산
            x = (i * step) + (step / 2)
            y = (j * step) + (step / 2)
            candidates.append({
                "id": f"Grid_{cand_id}", 
                "x": x, 
                "y": y
            })
            cand_id += 1
            
    return candidates

# 2. 시뮬레이션 실행 함수 (첫 번째 코드와 동일)
def run_simulation(loc_id, x, y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    content = content.replace("RSU_X_PLACEHOLDER", f"{x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{y:.2f}")
    
    with open(WORKING_INI, "w") as f:
        f.write(content)
        
    
    print(f" >>> [{loc_id}] 위치 (X:{x:.2f}, Y:{y:.2f}) 시뮬레이션 시작...", end=" ")
    
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
    return process.returncode

# 3. Throughput 파싱 함수 (첫 번째 코드와 동일)
def parse_throughput(sim_time):
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    received_packets = 0
    
    if not os.path.exists(result_path):
        return -1.0 # 에러 플래그
        
    try:
        with open(result_path, "r") as f:
            for line in f:
                if "receivedWSMs:count" in line:
                    received_packets = int(line.split()[-1])
                    break
        
        # Throughput (bps) 계산
        throughput_bps = (received_packets * 512 * 8) / sim_time
        return throughput_bps
    except Exception as e:
        print(f" [파싱 에러: 패킷 0개 간주]", end="")
        return 0

# --- 메인 실행부 ---
print("\n" + "="*60)
print(f"🚀 RSU 전역 탐색(Brute-force) 시작! (Grid Size: {GRID_SIZE}m)")
print("="*60)

# 후보지(Grid) 리스트 생성
candidates = generate_grid_centers(WIDTH, HEIGHT, GRID_SIZE)
print(f"총 {len(candidates)}개의 Grid 좌표가 생성되었습니다.\n")

final_data = []

# 순차적 시뮬레이션 구동
for idx, loc in enumerate(candidates):
    print(f"[{idx+1}/{len(candidates)}]", end="")
    run_simulation(loc["id"], loc["x"], loc["y"])
    
    tp = parse_throughput(SIM_TIME)
    print(f" => 결과: {tp:.2f} bps")
    
    final_data.append({
        "ID": loc["id"],
        "X": loc["x"], 
        "Y": loc["y"],
        "Throughput_bps": tp
    })

# 4. 결과 저장
df = pd.DataFrame(final_data)
df.to_csv(FINAL_CSV, index=False)

# 5. 시각화 (Grid 데이터가 많아 Bar Chart 대신 Heatmap 산점도로 변경)
plt.figure(figsize=(10, 10))

# Throughput 값이 높은 것을 두드러지게 표현 (RdYlGn 컬러맵)
sc = plt.scatter(df["X"], df["Y"], c=df["Throughput_bps"], cmap='RdYlGn', s=100, edgecolors='k', alpha=0.9)
plt.colorbar(sc, label='Throughput (bps)')

# 최고 성능 RSU 별표(*)로 강조
if not df.empty and df["Throughput_bps"].max() > 0:
    best_rsu = df.loc[df["Throughput_bps"].idxmax()]
    plt.scatter(best_rsu["X"], best_rsu["Y"], color='blue', marker='*', s=400, label=f'Best: {best_rsu["Throughput_bps"]:.1f} bps')
    plt.legend()

plt.xlim(0, WIDTH)
plt.ylim(0, HEIGHT)
plt.title(f"Grid-based RSU Throughput Optimization (Grid: {GRID_SIZE}m)")
plt.xlabel("X Coordinate (m)")
plt.ylabel("Y Coordinate (m)")
plt.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig("grid_throughput_heatmap.png")

print("\n" + "="*60)
print(f"모든 시뮬레이션 완료. 결과가 CSV와 Heatmap 이미지로 저장되었습니다.")
if not df.empty and df["Throughput_bps"].max() > 0:
    print(f"🏆 최고 성능: {best_rsu['ID']} (X:{best_rsu['X']:.1f}, Y:{best_rsu['Y']:.1f}) -> {best_rsu['Throughput_bps']:.1f} bps")
print("="*60)
