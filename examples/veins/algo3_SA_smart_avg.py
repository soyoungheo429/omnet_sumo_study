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
FINAL_CSV = "ms_asa_final_results.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# =========================================================
# 2. 다중 시작 & 적응형 SA 파라미터
# =========================================================
NUM_STARTS = 3         
T_START = 50.0         
T_END = 1.0            
ALPHA = 0.85           
MAX_ITER = 3           

MAX_STEP_SIZE = 150.0  
MIN_STEP_SIZE = 5.0    

# =========================================================
# 3. OMNeT++ 시뮬레이션 실행 및 PDR 파싱
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
# 4. 단일 에이전트의 적응형 SA (Adaptive SA) 알고리즘
# =========================================================
def run_single_agent_sa(agent_id, start_x, start_y):
    curr_x, curr_y = start_x, start_y
    curr_pdr = run_simulation(curr_x, curr_y)
    if curr_pdr < 0: curr_pdr = 0.0
    
    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = T_START
    history = []
    step_count = 1
    
    print(f"\n▶ [{agent_id}] 탐색 시작! 초기 위치(X:{curr_x:.1f}, Y:{curr_y:.1f}) | PDR: {curr_pdr:.2f}%")
    
    while temp > T_END:
        temp_ratio = (temp - T_END) / (T_START - T_END)
        current_step_limit = MIN_STEP_SIZE + (MAX_STEP_SIZE - MIN_STEP_SIZE) * temp_ratio
        
        for i in range(MAX_ITER):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, current_step_limit)
            next_x = curr_x + (math.cos(angle) * distance)
            next_y = curr_y + (math.sin(angle) * distance)
            
            next_x = max(0, min(WIDTH, next_x))
            next_y = max(0, min(HEIGHT, next_y))
            
            next_pdr = run_simulation(next_x, next_y)
            if next_pdr < 0: continue 

            delta = next_pdr - curr_pdr
            if delta > 0:
                accept = True
            else:
                acceptance_prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < acceptance_prob

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
            
            utm_x_back = curr_x + OFFSET_X 
            utm_y_back = curr_y + OFFSET_Y 
            lon, lat = utm_proj(utm_x_back, utm_y_back, inverse=True)
            history.append({
                "AgentID": agent_id, "Step": step_count, "Temp": temp, "StepLimit": current_step_limit,
                "X": curr_x, "Y": curr_y, "Lat": lat, "Lon": lon, "PDR": curr_pdr, 
                "IsBest": (curr_pdr == best_pdr)
            })
            step_count += 1
            
        print(f"  [{agent_id}] Temp: {temp:.1f} (보폭 {current_step_limit:.1f}m) -> 최고 PDR: {best_pdr:.2f}%")
        temp *= ALPHA
        
    return best_x, best_y, best_pdr, history

# =========================================================
# 5. 메인 루프: 다중 실행(Multi-Run) 알고리즘 안정성 검증
# =========================================================
NUM_RUNS = 6  # 논문 신뢰도를 확보하기 위한 10회 독립 실행 (필요 시 30회로 변경)

print("\n" + "="*60)
print(f"[Robustness Test] MS-ASA {NUM_RUNS}회 독립 실행 시작!")
print("="*60)

all_runs_history = []

for run_idx in range(1, NUM_RUNS + 1):
    print(f"\n" + "*"*40)
    print(f"  실행 회차: [ RUN {run_idx} / {NUM_RUNS} ] 시작")
    print("*"*40)
    
    run_history = []
    run_best_pdr = -1.0
    
    # 5명의 에이전트가 매 Run마다 완전히 새로운 무작위 위치에서 시작
    for i in range(1, NUM_STARTS + 1):
        start_x = random.uniform(0, WIDTH)
        start_y = random.uniform(0, HEIGHT)
        
        print(f"▶ Run {run_idx} - Agent_{i} 정밀 탐색 중...", end="\r")
        b_x, b_y, b_pdr, history = run_single_agent_sa(f"Agent_{i}", start_x, start_y)
        run_history.extend(history)
        
        if b_pdr > run_best_pdr:
            run_best_pdr = b_pdr
            
    # 이번 Run에 참여한 모든 에이전트의 기록 통합
    df_run = pd.DataFrame(run_history)
    
    # 각 Step(시간 흐름) 시점에서 5명 에이전트 중 최고값과 평균값 추출
    for step_num in sorted(df_run["Step"].unique()):
        step_data = df_run[df_run["Step"] == step_num]
        max_pdr_at_step = step_data["PDR"].max()
        avg_pdr_at_step = step_data["PDR"].mean()
        
        all_runs_history.append({
            "Run": run_idx,
            "Step": step_num,
            "Max_PDR": max_pdr_at_step,
            "Avg_PDR": avg_pdr_at_step
        })
        
    print(f"\nRun {run_idx} 완료! 최종 최고 PDR: {run_best_pdr:.2f}%")

# =========================================================
# 6. 결과 저장 및 논문용 에러바(음영) + 중앙값 시각화
# =========================================================
df = pd.DataFrame(all_runs_history)
df.to_csv("ms_asa_multirun_results.csv", index=False)

# 1. Step별 통계 계산 (10번의 Run 결과를 모아 평균, 중앙값, 표준편차 도출)
stats_max = df.groupby('Step')['Max_PDR'].agg(['mean', 'median', 'std']).reset_index()
stats_avg = df.groupby('Step')['Avg_PDR'].agg(['mean', 'median', 'std']).reset_index()

plt.figure(figsize=(10, 6))

# 2. [최고 PDR] 평균선 및 에러 음영 (빨간색 실선)
plt.plot(stats_max['Step'], stats_max['mean'], color='red', marker='o', markevery=5,
         linestyle='-', linewidth=2, label='Max PDR (Mean)')
plt.fill_between(stats_max['Step'], 
                 stats_max['mean'] - stats_max['std'], 
                 stats_max['mean'] + stats_max['std'], 
                 color='red', alpha=0.2, label='Max PDR (±1σ)')

# 3. [최고 PDR] 중앙값 선 추가 (녹색 점선) - 아웃라이어 방어용
plt.plot(stats_max['Step'], stats_max['median'], color='green', marker='^', markevery=5,
         linestyle=':', linewidth=2, label='Max PDR (Median)')

# 4. [평균 PDR] 평균선 및 에러 음영 (파란색 파선)
plt.plot(stats_avg['Step'], stats_avg['mean'], color='blue', marker='s', markevery=5,
         linestyle='--', linewidth=2, label='Population Avg PDR (Mean)')
plt.fill_between(stats_avg['Step'], 
                 stats_avg['mean'] - stats_avg['std'], 
                 stats_avg['mean'] + stats_avg['std'], 
                 color='blue', alpha=0.1)

plt.xlabel("Step (Iteration per Agent)", fontsize=12)
plt.ylabel("PDR (%)", fontsize=12)
plt.title(f"MS-ASA Convergence Robustness ({NUM_RUNS} Independent Runs)", fontsize=14)
plt.legend(loc='lower right', fontsize=10)
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()

plt.savefig("ms_asa_robustness_errorbar.png", dpi=300)
print("\n=> 'ms_asa_robustness_errorbar.png' 논문용 신뢰도 차트 저장 완료!")

