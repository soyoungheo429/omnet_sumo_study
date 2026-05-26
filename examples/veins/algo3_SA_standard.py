import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import math
import random
import folium
from pyproj import Proj

# 1. 시뮬레이션 및 맵 설정값
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "algo3_sa_results.csv"

# 에를랑겐 맵 설정 (algo2와 동일)
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

# 좌표 변환 설정
proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# 2. Simulated Annealing 파라미터
T_START = 10.0      # 시작 온도
T_END = 0.1        # 종료 온도
ALPHA = 0.85       # 냉각 속도
MAX_ITER = 3       # 각 온도 단계에서의 반복 횟수 (테스트를 위해 작게 설정)
STEP_SIZE = 150.0   # 최대 이동 거리 (m)

# 3. OMNeT++ 시뮬레이션 실행 및 PDR 파싱
def run_simulation(sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    content = content.replace("RSU_X_PLACEHOLDER", f"{sim_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{sim_y:.2f}")
    with open(WORKING_INI, "w") as f:
        f.write(content)
    
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
    
    if process.returncode != 0 or "<!> Error" in process.stdout or "<!> Error" in process.stderr:
        return -1.0
        
    return parse_pdr()

def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    total_received = 0
    rsu_generated = 0
    node_count = 0

    if not os.path.exists(result_path): return 0.0

    try:
        with open(result_path, "r") as f:
            content = f.read()

            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match: rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            for val in node_recv_matches:
                total_received += int(val)
                node_count += 1

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles

        if expected_total == 0: return 0.0

        pdr = (total_received / expected_total) * 100
        return pdr
    except Exception as e:
        print(f"파싱 에러: {e}")
        return 0.0

# 4. Simulated Annealing 알고리즘 구현
def simulated_annealing():
    # 초기해 설정 (랜덤)
    curr_x = random.uniform(0, WIDTH)
    curr_y = random.uniform(0, HEIGHT)
    curr_pdr = run_simulation(curr_x, curr_y)
    
    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    
    temp = T_START
    history = []
    
    step_count = 1
    total_steps = int(math.log(T_END / T_START) / math.log(ALPHA)) * MAX_ITER
    
    print(f"\n🚀 Simulated Annealing 시작 (초기 PDR: {curr_pdr:.2f}%)")
    
    while temp > T_END:
        for i in range(MAX_ITER):
            # 이웃해 생성 (현재 위치에서 STEP_SIZE 내로 랜덤 이동)
            next_x = max(0, min(WIDTH, curr_x + random.uniform(-STEP_SIZE, STEP_SIZE)))
            next_y = max(0, min(HEIGHT, curr_y + random.uniform(-STEP_SIZE, STEP_SIZE)))
            
            print(f" [{step_count}] Temp: {temp:.2f} | 시도 위치 (X: {next_x:.1f}, Y: {next_y:.1f})... ", end="")
            
            next_pdr = run_simulation(next_x, next_y)
            
            if next_pdr < 0:
                print("에러 발생 (스킵)")
                continue

            # 수락 여부 결정
            delta = next_pdr - curr_pdr
            
            if delta > 0:
                # 더 좋은 해면 무조건 수락
                accept = True
                reason = "개선됨"
            else:
                # 더 나쁜 해면 확률적으로 수락
                acceptance_prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < acceptance_prob
                reason = f"확률적 수락 (prob: {acceptance_prob:.3f})" if accept else "거절"

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
                    reason += " [NEW BEST!]"
                print(f"수락: {next_pdr:.2f}% ({reason})")
            else:
                print(f"거절: {next_pdr:.2f}%")

            lon, lat = utm_proj(curr_x + OFFSET_X, curr_y + OFFSET_Y, inverse=True)
            history.append({
                "Step": step_count,
                "Temp": temp,
                "X": curr_x,
                "Y": curr_y,
                "Lat": lat,
                "Lon": lon,
                "PDR": curr_pdr,
                "Accepted": accept,
                "IsBest": (curr_pdr == best_pdr)
            })
            step_count += 1
            
        temp *= ALPHA
        
    return best_x, best_y, best_pdr, history

# 5. 메인 실행
#random.seed(42) # 재현성을 위해 시드 고정
best_x, best_y, best_pdr, history = simulated_annealing()

# 결과 저장
df = pd.DataFrame(history)
df.to_csv(FINAL_CSV, index=False)

print("\n" + "="*50)
print("Simulated Annealing 최적화 완료!")
print(f"최적 위치: X={best_x:.2f}, Y={best_y:.2f}")
print(f"최고 PDR: {best_pdr:.2f}%")
print("="*50)

# 시각화 (Convergence Plot)
plt.figure(figsize=(10, 5))
plt.plot(df["Step"], df["PDR"], marker='o', linestyle='-', color='b', label='Current PDR')
plt.plot(df[df["IsBest"]]["Step"], df[df["IsBest"]]["PDR"], 'ro', label='Best PDR')
plt.xlabel("Step")
plt.ylabel("PDR (%)")
plt.title("Simulated Annealing Convergence")
plt.legend()
plt.grid(True)
plt.savefig("algo3_sa_convergence.png")

# Folium 지도 생성
best_lon, best_lat = utm_proj(best_x + OFFSET_X, best_y + OFFSET_Y, inverse=True)
m = folium.Map(location=[best_lat, best_lon], zoom_start=15)

# 경로 시각화
path_coords = []
for idx, row in df.iterrows():
    path_coords.append([row["Lat"], row["Lon"]])
    folium.CircleMarker(
        location=[row["Lat"], row["Lon"]],
        radius=3,
        color="gray" if not row["IsBest"] else "red",
        popup=f"Step {row['Step']}: {row['PDR']:.2f}%"
    ).add_to(m)

folium.PolyLine(path_coords, color="blue", weight=2, opacity=0.5).add_to(m)
folium.Marker(
    location=[best_lat, best_lon],
    popup=f"BEST: {best_pdr:.2f}%",
    icon=folium.Icon(color='red', icon='star')
).add_to(m)

m.save("algo3_sa_map.html")
print("=> 'algo3_sa_convergence.png' 및 'algo3_sa_map.html' 저장 완료")
lium.Marker(
    location=[best_lat, best_lon],
    popup=f"BEST: {best_pdr:.2f}%",
    icon=folium.Icon(color='red', icon='star')
).add_to(m)

m.save("algo3_sa_map.html")
print("=> 'algo3_sa_convergence.png' 및 'algo3_sa_map.html' 저장 완료")

