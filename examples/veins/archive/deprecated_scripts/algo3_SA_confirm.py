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

# =========================================================
# 1. 시뮬레이션 및 맵 설정값
# =========================================================
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "algo3_sa_confirm_results.csv"
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
SEARCH_RADIUS = 300.0  # 이 반경 안에서만 탐색

# GPS 위경도 변환용
proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# =========================================================
# 2. 스마트 SA 파라미터 (Adaptive + Multi-Start)
# =========================================================
NUM_STARTS = 3         
T_START = 10.0         
T_END = 0.1            
ALPHA = 0.85           
MAX_ITER = 3           

MAX_STEP_SIZE = 150.0   
MIN_STEP_SIZE = 5.0    

# =========================================================
# 3. 시뮬레이션 및 파싱 함수
# =========================================================
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
def run_single_agent_sa(agent_id, start_x, start_y):
    curr_x, curr_y = start_x, start_y
    curr_pdr = run_simulation(curr_x, curr_y)
    if curr_pdr < 0: curr_pdr = 0.0
    
    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = T_START
    history = []
    step_count = 1
    
    print(f"\n▶ [{agent_id}] 정밀 탐색 시작! 위치(X:{curr_x:.1f}, Y:{curr_y:.1f}) | PDR: {curr_pdr:.2f}%")
    
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
                "AgentID": agent_id, "Step": step_count, "Temp": temp, 
                "X": curr_x, "Y": curr_y, "Lat": lat, "Lon": lon, "PDR": curr_pdr, 
                "IsBest": (curr_pdr == best_pdr)
            })
            step_count += 1
            
        temp *= ALPHA
    return best_x, best_y, best_pdr, history

# =========================================================
# 5. 메인 실행
# =========================================================
print("\n" + "="*60)
print(f"[Confirming with Smart SA] 반경 {SEARCH_RADIUS}m 정밀 최적화 시작")
print("="*60)

all_history = []
global_best_pdr = -1.0
global_best_x, global_best_y = 0, 0

for i in range(1, NUM_STARTS + 1):
    s_x = START_X + random.uniform(-10, 10)
    s_y = START_Y + random.uniform(-10, 10)
    
    b_x, b_y, b_pdr, history = run_single_agent_sa(f"Agent_{i}", s_x, s_y)
    all_history.extend(history)
    
    if b_pdr > global_best_pdr:
        global_best_pdr, global_best_x, global_best_y = b_pdr, b_x, b_y

df = pd.DataFrame(all_history)
df.to_csv(FINAL_CSV, index=False)

print("\n" + "="*50)
print("GA 최적화 완료!")
print(f"최종 최고 PDR: {global_best_pdr:.2f}% (X={global_best_x:.2f}, Y={global_best_y:.2f})")
print("="*50)

# 시각화 1. Convergence
plt.figure(figsize=(10, 5))
for agent_id in df["AgentID"].unique():
    agent_data = df[df["AgentID"] == agent_id]
    plt.plot(agent_data["Step"], agent_data["PDR"], label=agent_id, alpha=0.7)
plt.xlabel("Step")
plt.ylabel("PDR (%)")
plt.title(f"Refinement SA within {SEARCH_RADIUS}m")
plt.legend()
plt.grid(True)
plt.savefig("algo3_sa_confirm_convergence.png")

# 지도 시각화
best_lon, best_lat = utm_proj(global_best_x + OFFSET_X - 50, global_best_y + OFFSET_Y + 300, inverse=True)
m = folium.Map(location=[best_lat, best_lon], zoom_start=17)
folium.Circle(
    location=[utm_proj(START_X + OFFSET_X - 50, START_Y + OFFSET_Y + 300, inverse=True)[1], 
              utm_proj(START_X + OFFSET_X - 50, START_Y + OFFSET_Y + 300, inverse=True)[0]],
    radius=SEARCH_RADIUS, color="green", fill=True, fill_opacity=0.1
).add_to(m)

colors = ['blue', 'purple', 'orange']
for idx, agent_id in enumerate(df["AgentID"].unique()):
    agent_data = df[df["AgentID"] == agent_id]
    path_coords = [[row["Lat"], row["Lon"]] for _, row in agent_data.iterrows()]
    folium.PolyLine(path_coords, color=colors[idx % 3], weight=2, opacity=0.6).add_to(m)

folium.Marker(location=[best_lat, best_lon], popup=f"Final Best: {global_best_pdr:.2f}%", icon=folium.Icon(color='red')).add_to(m)
m.save("algo3_sa_confirm_map.html")

