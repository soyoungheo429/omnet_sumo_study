import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import math
import random
import folium
import statistics
from pyproj import Proj

# =========================================================
# 1. 시뮬레이션 및 맵 설정값
# =========================================================
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "algo3_sa_confirm_avg_results.csv"
ALGO1_RESULT_CSV = "rsu_pdr_optimization_results.csv"

# 에를랑겐 맵 오프셋 및 크기
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

# [자동화] Algo1 최적점 불러오기
def load_best_from_algo1():
    if not os.path.exists(ALGO1_RESULT_CSV):
        print(f"{ALGO1_RESULT_CSV} 파일이 없습니다. 기본 좌표를 사용합니다.")
        return 515.22, 1455.51
        
    df_algo1 = pd.read_csv(ALGO1_RESULT_CSV)
    best_row = df_algo1.loc[df_algo1["PDR"].idxmax()]
    print(f"Algo1 최적점 로드 완료: ID={best_row['ID']}, PDR={best_row['PDR']:.2f}%")
    return best_row["Sim_X"], best_row["Sim_Y"]

START_X, START_Y = load_best_from_algo1()
SEARCH_RADIUS = 150.0  # 이 반경 안에서만 탐색

# GPS 위경도 변환용
proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# =========================================================
# 2. 스마트 SA 파라미터 (Adaptive + Multi-Start)
# =========================================================
NUM_STARTS = 3         
T_START = 10.0         
T_END = 0.5            
ALPHA = 0.85           
MAX_ITER = 3           

MAX_STEP_SIZE = 75.0   
MIN_STEP_SIZE = 3.0    

# =========================================================
# 3. 시뮬레이션 및 파싱 함수
# =========================================================
def run_simulation(sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    # 플레이스홀더 좌표 교체
    content = content.replace("RSU_X_PLACEHOLDER", f"{sim_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{sim_y:.2f}")
    
    # 매번 완전히 무작위인 트래픽 시나리오 강제 주입
    random_traffic_seed = random.randint(0, 999999)
    content += f"\n\nseed-set = {random_traffic_seed}\n"
    
    with open(WORKING_INI, "w") as f:
        f.write(content)
        
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
        
    if process.returncode != 0 or "<!> Error" in process.stdout or "<!> Error" in process.stderr:
        return -1.0
            
    return parse_pdr()

def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path): return 0.0

    try:
        total_received, rsu_generated, node_count = 0, 0, 0
        with open(result_path, "r") as f:
            content = f.read()

            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match: rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(r"node\[(\d+)\].appl\s+receivedBSMs\s+(\d+)", content)
            nodes_found = set()
            for node_idx, val in node_recv_matches:
                total_received += int(val)
                nodes_found.add(node_idx)
            node_count = len(nodes_found)

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles

        if expected_total == 0: return 0.0
        return (total_received / expected_total) * 100
    except Exception as e:
        print(f"파싱 에러: {e}")
        return 0.0

# =========================================================
# 4. Adaptive SA 에이전트 로직
# =========================================================
def run_single_agent_sa(agent_id, start_x, start_y, run_idx=1):
    curr_x, curr_y = start_x, start_y
    curr_pdr = run_simulation(curr_x, curr_y)
    if curr_pdr < 0: curr_pdr = 0.0
    
    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = T_START
    history = []
    step_count = 1
    
    print(f"▶ [Run {run_idx} - {agent_id}] 정밀 탐색 시작! 위치({curr_x:.1f}, {curr_y:.1f}) | PDR: {curr_pdr:.2f}%")
    
    while temp > T_END:
        temp_ratio = (temp - T_END) / (T_START - T_END)
        current_step_limit = MIN_STEP_SIZE + (MAX_STEP_SIZE - MIN_STEP_SIZE) * temp_ratio
        
        for i in range(MAX_ITER):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, current_step_limit)
            
            next_x = curr_x + (math.cos(angle) * distance)
            next_y = curr_y + (math.sin(angle) * distance)
            
            dist_from_start = math.sqrt((next_x - START_X)**2 + (next_y - START_Y)**2)
            if dist_from_start > SEARCH_RADIUS:
                scale = SEARCH_RADIUS / dist_from_start
                next_x = START_X + (next_x - START_X) * scale
                next_y = START_Y + (next_y - START_Y) * scale
            
            next_x = max(0, min(WIDTH, next_x))
            next_y = max(0, min(HEIGHT, next_y))
            
            next_pdr = run_simulation(next_x, next_y)
            if next_pdr < 0: continue

            delta = next_pdr - curr_pdr
            if delta > 0:
                accept = True
            else:
                prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < prob

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
            
            utm_x_back = curr_x + OFFSET_X - 50
            utm_y_back = curr_y + OFFSET_Y + 300
            lon, lat = utm_proj(utm_x_back, utm_y_back, inverse=True)
            history.append({
                "Run": run_idx, "AgentID": agent_id, "Step": step_count, "Temp": temp, 
                "X": curr_x, "Y": curr_y, "Lat": lat, "Lon": lon, "PDR": curr_pdr, 
                "IsBest": (curr_pdr == best_pdr)
            })
            step_count += 1
            
        temp *= ALPHA
    return best_x, best_y, best_pdr, history

# =========================================================
# 5. 메인 실행 (Multi-Run으로 확장)
# =========================================================
NUM_RUNS = 8  # 총 1400번 정도 돌리기 위해 (8 runs * 3 agents * 57 iterations ≈ 1368)

print("\n" + "="*60)
print(f"[Confirming with Smart SA] {NUM_RUNS}회 반복 실행 시작 (총 약 1400회 시뮬레이션)")
print(f"중심 위치: (X={START_X:.2f}, Y={START_Y:.2f}), 반경: {SEARCH_RADIUS}m")
print("="*60)

all_runs_summary = []
all_history_for_plot = []
global_best_pdr = -1.0
global_best_x, global_best_y = 0, 0
best_run_history = []

for run_idx in range(1, NUM_RUNS + 1):
    print(f"\n[ RUN {run_idx} / {NUM_RUNS} ]")
    
    # [핵심 변경] seed 안쪽을 완전히 비워서 매 실행(Run)마다 100% 무작위 위치를 생성하게 유도합니다.
    random.seed()
    
    run_history = []
    run_best_pdr = -1.0
    
    for i in range(1, NUM_STARTS + 1):
        # 150m 울타리 반경 내에 3명의 에이전트를 골고루 분산시켜 시작 (공백 정렬 완료)
        init_angle = random.uniform(0, 2 * math.pi)
        init_dist = random.uniform(0, SEARCH_RADIUS)
        s_x = START_X + (math.cos(init_angle) * init_dist)
        s_y = START_Y + (math.sin(init_angle) * init_dist)
        
        b_x, b_y, b_pdr, history = run_single_agent_sa(f"Agent_{i}", s_x, s_y, run_idx)
        run_history.extend(history)
        
        if b_pdr > run_best_pdr:
            run_best_pdr = b_pdr
            
        if b_pdr > global_best_pdr:
            global_best_pdr, global_best_x, global_best_y = b_pdr, b_x, b_y
            best_run_history = history # 시각화용 (최고 기록 에이전트 경로)

    # Step별 통계 수집 (Plotting용)
    df_run = pd.DataFrame(run_history)
    for step_num in sorted(df_run["Step"].unique()):
        step_data = df_run[df_run["Step"] == step_num]
        all_history_for_plot.append({
            "Run": run_idx,
            "Step": step_num,
            "Max_PDR": step_data["PDR"].max(),
            "Avg_PDR": step_data["PDR"].mean()
        })
    
    print(f"Run {run_idx} 완료! 최고 PDR: {run_best_pdr:.2f}%")

# 결과 데이터프레임 저장
df_plot = pd.DataFrame(all_history_for_plot)
df_plot.to_csv(FINAL_CSV, index=False)

print("\n" + "="*50)
print("모든 실행 완료!")
print(f"전체 최고 PDR: {global_best_pdr:.2f}% (X={global_best_x:.2f}, Y={global_best_y:.2f})")
print("="*50)

# 시각화: Errorbar Plot (algo3_SA_smart2_avg.py 스타일)
stats_max = df_plot.groupby('Step')['Max_PDR'].agg(['mean', 'std']).reset_index()
stats_avg = df_plot.groupby('Step')['Avg_PDR'].agg(['mean', 'std']).reset_index()

plt.figure(figsize=(10, 6))
plt.plot(stats_max['Step'], stats_max['mean'], color='red', label='Max PDR (Mean)')
plt.fill_between(stats_max['Step'], stats_max['mean'] - stats_max['std'], stats_max['mean'] + stats_max['std'], color='red', alpha=0.2)

plt.plot(stats_avg['Step'], stats_avg['mean'], color='blue', linestyle='--', label='Avg PDR (Mean)')
plt.fill_between(stats_avg['Step'], stats_avg['mean'] - stats_avg['std'], stats_avg['mean'] + stats_avg['std'], color='blue', alpha=0.1)

plt.xlabel("Step")
plt.ylabel("PDR (%)")
plt.title(f"SA Refinement Robustness ({NUM_RUNS} runs, total ~1400 iterations)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.savefig("algo3_sa_confirm_robustness.png")

# 지도 시각화 (전체 최고 결과 기준)
best_lon, best_lat = utm_proj(global_best_x + OFFSET_X - 50, global_best_y + OFFSET_Y + 300, inverse=True)
m = folium.Map(location=[best_lat, best_lon], zoom_start=17)
folium.Circle(
    location=[utm_proj(START_X + OFFSET_X - 50, START_Y + OFFSET_Y + 300, inverse=True)[1], 
              utm_proj(START_X + OFFSET_X - 50, START_Y + OFFSET_Y + 300, inverse=True)[0]],
    radius=SEARCH_RADIUS, color="green", fill=True, fill_opacity=0.1
).add_to(m)

folium.Marker(location=[best_lat, best_lon], popup=f"Global Best: {global_best_pdr:.2f}%", icon=folium.Icon(color='red')).add_to(m)
m.save("algo3_sa_confirm_map.html")
