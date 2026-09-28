import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import math
import random
import statistics  # 중앙값 계산용 추가
import folium
from pyproj import Proj

# =========================================================
# 1. 시뮬레이션 및 맵 설정값
# =========================================================
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "ms_asa_paper_params_results.csv"

# 에를랑겐 맵 오프셋 및 크기
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# =========================================================
# 2. 다중 시작 & 적응형 SA 파라미터 (논문 공식 적용!)
# =========================================================
NUM_STARTS = 5         # 파견할 탐색가(Agent) 수
ALPHA = 0.3981         # [논문 적용] 기하급수적 냉각 속도
MAX_ITER = 10          # [논문 적용] 각 온도 단계에서의 반복 탐색 횟수

# [적응형 보폭 조절] 초반엔 크게, 후반엔 정밀하게 (연속 공간 탐색용)
MAX_STEP_SIZE = 150.0  # 초반 최대 이동 거리 (m)
MIN_STEP_SIZE = 5.0    # 후반 최소 미세조정 거리 (m)

# (T_START와 T_END는 아래 함수를 통해 논문 수식으로 자동 계산됩니다)

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
            nodes = set()
            for node_idx, val in node_recv_matches:
                total_received += int(val)
                nodes.add(node_idx)
            node_count = len(nodes)

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles
        if expected_total == 0: return 0.0
        return (total_received / expected_total) * 100
    except:
        return 0.0

# =========================================================
# [핵심] 논문 기반 초기 파라미터(온도) 동적 계산 함수
# =========================================================
def calculate_initial_parameters(sample_size=10): 
    print("\n" + "="*60)
    print("[논문 수식 적용] 초기 온도(T0) 결정을 위한 무작위 샘플링 중...")
    
    pdrs = []
    for i in range(sample_size):
        x = random.uniform(0, WIDTH)
        y = random.uniform(0, HEIGHT)
        pdr = run_simulation(x, y)
        if pdr >= 0:
            pdrs.append(pdr)
            print(f"  -> 샘플 {i+1}: PDR {pdr:.2f}%")

    # [핵심 방어 1] 0.0%인 꽝 자리는 중앙값 계산에서 아예 제외
    valid_pdrs = [p for p in pdrs if p > 0.1] # 0.1% 이상인 의미 있는 값만 추출

    if not valid_pdrs:
        median_pdr = 10.0  # 의미 있는 샘플이 아예 없다면 기본값 10.0 부여
    else:
        median_pdr = statistics.median(valid_pdrs)

    # [논문 수식 1] 초기 온도 = 중앙값 / ln(2)
    t_start = median_pdr / math.log(2)
    
    # [핵심 방어 2] PDR 스케일에 맞게 최소한의 관대함(온도 10.0도) 보장
    # 온도가 최소 10도는 되어야 -1~-2% 떨어지는 걸 어느 정도 수락해 줍니다.
    if t_start < 10.0: 
        t_start = 10.0

    # [논문 수식 2] 종료 온도 = 초기 온도의 10^-4 배
    t_end = t_start * 1e-4

    print(f"\n=> 유효 샘플 PDR 중앙값(M) : {median_pdr:.2f}%")
    print(f"=> 보정된 초기 온도(T_0): {t_start:.4f}")
    print(f"=> 보정된 종료 온도(T_n): {t_end:.6f}")
    print("="*60 + "\n")
    return t_start, t_end

# =========================================================
# 4. 단일 에이전트의 적응형 SA (Adaptive SA) 알고리즘
# =========================================================
def run_single_agent_sa(agent_id, start_x, start_y, t_start, t_end):
    curr_x, curr_y = start_x, start_y
    curr_pdr = run_simulation(curr_x, curr_y)
    if curr_pdr < 0: curr_pdr = 0.0
    
    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = t_start
    history = []
    step_count = 1
    
    print(f"▶ [{agent_id}] 탐색 시작! 초기 위치(X:{curr_x:.1f}, Y:{curr_y:.1f}) | PDR: {curr_pdr:.2f}%")
    
    while temp > t_end:
        # [핵심] 온도에 비례하여 보폭(Step Size) 축소
        temp_ratio = (temp - t_end) / (t_start - t_end)
        current_step_limit = MIN_STEP_SIZE + (MAX_STEP_SIZE - MIN_STEP_SIZE) * temp_ratio
        
        for i in range(MAX_ITER):
            # 원형 범위 내에서 새로운 연속 좌표 생성
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, current_step_limit)
            next_x = curr_x + (math.cos(angle) * distance)
            next_y = curr_y + (math.sin(angle) * distance)
            
            # 맵 경계 밖으로 나가면 보정
            next_x = max(0, min(WIDTH, next_x))
            next_y = max(0, min(HEIGHT, next_y))
            
            next_pdr = run_simulation(next_x, next_y)
            if next_pdr < 0: continue # 에러 발생 시 스킵

            delta = next_pdr - curr_pdr
            
            if delta > 0:
                accept, reason = True, "개선됨"
            else:
                acceptance_prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < acceptance_prob
                reason = f"확률 수락({acceptance_prob:.2f})" if accept else "거절"

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
                    reason += " [NEW BEST!]"
            
            lon, lat = utm_proj(curr_x + OFFSET_X, curr_y + OFFSET_Y, inverse=True)
            history.append({
                "AgentID": agent_id, "Step": step_count, "Temp": temp, "StepLimit": current_step_limit,
                "X": curr_x, "Y": curr_y, "Lat": lat, "Lon": lon, "PDR": curr_pdr, 
                "Accepted": accept, "IsBest": (curr_pdr == best_pdr)
            })
            step_count += 1
            
        print(f"  [{agent_id}] Temp: {temp:.4f} (보폭 {current_step_limit:.1f}m) -> 최고 PDR: {best_pdr:.2f}%")
        temp *= ALPHA # 논문의 0.3981 냉각 속도 적용
        
    print(f"  [{agent_id}] 완료! 최고 기록: {best_pdr:.2f}%\n")
    return best_x, best_y, best_pdr, history

# =========================================================
# 5. 메인: 다중 시작(Multi-Start) 제어 및 시각화
# =========================================================
random.seed(42)  # 논문 데이터 추출용 시드 고정

# [추가됨] 본격적인 시작 전, 온도를 먼저 동적으로 계산합니다!
global_t_start, global_t_end = calculate_initial_parameters(sample_size=10)

print("="*60)
print(f"[Multi-Start Adaptive SA] {NUM_STARTS}명의 탐색가 파견 시작!")
print("="*60)

all_history = []
global_best_pdr = -1.0
global_best_x, global_best_y = 0, 0

for i in range(1, NUM_STARTS + 1):
    start_x = random.uniform(0, WIDTH)
    start_y = random.uniform(0, HEIGHT)
    
    b_x, b_y, b_pdr, history = run_single_agent_sa(f"Agent_{i}", start_x, start_y, global_t_start, global_t_end)
    all_history.extend(history)
    
    if b_pdr > global_best_pdr:
        global_best_pdr, global_best_x, global_best_y = b_pdr, b_x, b_y

# (이하 결과 CSV 저장 및 그래프/지도 시각화 코드는 기존 코드 100% 동일하므로 생략하지 않고 모두 포함)
df = pd.DataFrame(all_history)
df.to_csv(FINAL_CSV, index=False)

print("\n" + "★"*60)
print("MS-ASA 최적화 완료")
print(f"최종 완벽 명당 좌표: X={global_best_x:.2f}, Y={global_best_y:.2f}")
print(f"달성한 최고 PDR    : {global_best_pdr:.2f}%")
print("★"*60)

# 시각화 1. Convergence Plot
plt.figure(figsize=(12, 6))
colors = ['blue', 'green', 'purple', 'orange', 'cyan', 'red', 'brown', 'pink', 'gray', 'olive']

for idx, agent_id in enumerate(df["AgentID"].unique()):
    agent_data = df[df["AgentID"] == agent_id]
    plt.plot(agent_data["Step"], agent_data["PDR"], marker='.', linestyle='-', 
             color=colors[idx % len(colors)], alpha=0.6, label=agent_id)

global_best_row = df.loc[df["PDR"].idxmax()]
plt.plot(global_best_row["Step"], global_best_row["PDR"], 'r*', markersize=15, label='Global Best')

plt.xlabel("Step (per Agent)")
plt.ylabel("PDR (%)")
plt.title("Multi-Start Adaptive SA Convergence")
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.grid(True)
plt.tight_layout()
plt.savefig("ms_asa_paper_convergence.png")

# 시각화 2. Folium 지도
best_lon, best_lat = utm_proj(global_best_x + OFFSET_X, global_best_y + OFFSET_Y, inverse=True)
m = folium.Map(location=[best_lat, best_lon], zoom_start=14, tiles='CartoDB Positron')

for idx, agent_id in enumerate(df["AgentID"].unique()):
    agent_data = df[df["AgentID"] == agent_id]
    color = colors[idx % len(colors)]
    path_coords = []
    
    for _, row in agent_data.iterrows():
        path_coords.append([row["Lat"], row["Lon"]])
        folium.CircleMarker(
            location=[row["Lat"], row["Lon"]],
            radius=2, color=color, opacity=0.5,
            popup=f"{agent_id} Step {row['Step']}: {row['PDR']:.1f}%"
        ).add_to(m)
        
    folium.PolyLine(path_coords, color=color, weight=2, opacity=0.6, popup=agent_id).add_to(m)

folium.Marker(
    location=[best_lat, best_lon],
    popup=f"<b>GLOBAL BEST</b><br>PDR: {global_best_pdr:.2f}%",
    icon=folium.Icon(color='red', icon='star')
).add_to(m)

folium.Circle(
    location=[best_lat, best_lon],
    radius=150, color="red", weight=2, fill=True, fill_opacity=0.1
).add_to(m)

m.save("ms_asa_paper_map.html")
print("=> 시각화 파일 생성 완료")
