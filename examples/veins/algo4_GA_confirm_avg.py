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
FINAL_CSV = "ga_multirun_results.csv"
ALGO1_RESULT_CSV = "rsu_pdr_optimization_results.csv" # Algo1 결과 파일 추가

# 에를랑겐 맵 설정
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
SEARCH_RADIUS = 150.0  # 이 반경 안에서만 탐색 (SA와 공정 비교용)

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# =========================================================
# 2. 유전 알고리즘(GA) 파라미터
# =========================================================
POP_SIZE = 10           # 개체군 크기 (한 세대당 탐색가 수)
MAX_GENERATIONS = 10    # 총 진화 세대 수
ELITISM_COUNT = 1       # 엘리트 보존 수 (가장 우수한 1명은 무조건 생존)

# [적응형 시그마] 돌연변이 폭발 반경 (초반엔 크게, 후반엔 좁게)
MAX_SIGMA = 150.0
MIN_SIGMA = 5.0         # 5m (막판 건물 모퉁이 미세 조정)

# =========================================================
# 3. OMNeT++ 시뮬레이션 및 적합도(PDR) 평가 함수
# =========================================================
def run_simulation(sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    content = content.replace("RSU_X_PLACEHOLDER", f"{sim_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{sim_y:.2f}")
    
    # [복구] 지난번 적용했던 무작위 트래픽 시드 로직 강제 주입
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
# 4. GA 핵심 연산자: 하이브리드 교차 및 돌연변이
# =========================================================
def tournament_selection(population):
    """토너먼트 선택: 무작위 3명 중 1등(부모) 선발"""
    competitors = random.sample(population, 3)
    competitors.sort(key=lambda ind: ind['pdr'], reverse=True)
    return competitors[0]

def crossover_and_mutate(parent1, parent2, current_gen):
    """가중 평균 교차 + 적응형 가우시안 돌연변이 결합"""
    
    total_pdr = parent1['pdr'] + parent2['pdr']
    if total_pdr <= 0:
        w1, w2 = 0.5, 0.5
    else:
        w1 = parent1['pdr'] / total_pdr
        w2 = parent2['pdr'] / total_pdr
        
    m_x = (parent1['x'] * w1) + (parent2['x'] * w2)
    m_y = (parent1['y'] * w1) + (parent2['y'] * w2)
    
    ratio = current_gen / MAX_GENERATIONS
    current_sigma = MAX_SIGMA - (MAX_SIGMA - MIN_SIGMA) * ratio
    
    child_x = random.gauss(m_x, current_sigma)
    child_y = random.gauss(m_y, current_sigma)
    
    # [추가] 자식 개체가 150m 반경 밖으로 돌연변이하면 울타리 안으로 다시 끌어당김
    dist_from_start = math.sqrt((child_x - START_X)**2 + (child_y - START_Y)**2)
    if dist_from_start > SEARCH_RADIUS:
        scale = SEARCH_RADIUS / dist_from_start
        child_x = START_X + (child_x - START_X) * scale
        child_y = START_Y + (child_y - START_Y) * scale
    
    child_x = max(0, min(WIDTH, child_x))
    child_y = max(0, min(HEIGHT, child_y))
    
    return child_x, child_y

# =========================================================
# 5. 메인 루프: 다중 실행(Multi-Run) 알고리즘 안정성 검증
# =========================================================
NUM_RUNS = 15  # 시뮬레이션 횟수를 약 1,365회로 타겟팅

print("\n" + "="*60)
print(f"[Robustness Test] GA {NUM_RUNS}회 독립 실행 시작!")
print(f"중심 위치: (X={START_X:.2f}, Y={START_Y:.2f}), 반경: {SEARCH_RADIUS}m")
print("="*60)

all_runs_history = []

for run_idx in range(1, NUM_RUNS + 1):
    print(f"\n" + "▼"*40)
    print(f"  실행 회차: [ RUN {run_idx} / {NUM_RUNS} ] 시작")
    print("▼"*40)
    
    # 매번 완전히 새로운 무작위 난수 시드 배정
    random.seed()
    run_best_pdr = -1.0
    
    # [수정] 초기 개체군 10명을 맵 전체가 아닌 'Algo1 명당 주변 150m' 안에 원형으로 흩뿌림
    population = []
    for _ in range(POP_SIZE):
        init_angle = random.uniform(0, 2 * math.pi)
        init_dist = random.uniform(0, SEARCH_RADIUS)
        init_x = START_X + (math.cos(init_angle) * init_dist)
        init_y = START_Y + (math.sin(init_angle) * init_dist)
        
        init_x = max(0, min(WIDTH, init_x))
        init_y = max(0, min(HEIGHT, init_y))
        population.append({'x': init_x, 'y': init_y, 'pdr': 0.0})

    for gen in range(1, MAX_GENERATIONS + 1):
        print(f"▶ Run {run_idx} - [Gen {gen}/{MAX_GENERATIONS}] 평가 중...", end="\r")
        
        for i, ind in enumerate(population):
            if ind['pdr'] == 0.0:
                ind['pdr'] = run_simulation(ind['x'], ind['y'])
            
            if ind['pdr'] > run_best_pdr:
                run_best_pdr = ind['pdr']
                
        population.sort(key=lambda item: item['pdr'], reverse=True)
        gen_max_pdr = population[0]['pdr']
        gen_avg_pdr = sum(ind['pdr'] for ind in population) / POP_SIZE
        
        all_runs_history.append({
            "Run": run_idx,
            "Gen": gen,
            "Max_PDR": gen_max_pdr,
            "Avg_PDR": gen_avg_pdr
        })
        
        if gen == MAX_GENERATIONS: break
            
        next_population = []
        for i in range(ELITISM_COUNT): 
            next_population.append(population[i].copy())
            
        while len(next_population) < POP_SIZE: 
            p1 = tournament_selection(population)
            p2 = tournament_selection(population)
            c_x, c_y = crossover_and_mutate(p1, p2, gen)
            next_population.append({'x': c_x, 'y': c_y, 'pdr': 0.0})
            
        population = next_population
        
    print(f"\nRun {run_idx} 완료! 최종 최고 PDR: {run_best_pdr:.2f}%")

# =========================================================
# 6. 결과 저장 및 논문용 에러바(음영) 시각화
# =========================================================
df = pd.DataFrame(all_runs_history)
df.to_csv(FINAL_CSV, index=False)

stats_max = df.groupby('Gen')['Max_PDR'].agg(['mean', 'std']).reset_index()
stats_avg = df.groupby('Gen')['Avg_PDR'].agg(['mean', 'std']).reset_index()

plt.figure(figsize=(10, 6))

plt.plot(stats_max['Gen'], stats_max['mean'], color='red', marker='o', 
         linestyle='-', linewidth=2, label='Generation Best PDR (Mean)')
plt.fill_between(stats_max['Gen'], 
                 stats_max['mean'] - stats_max['std'], 
                 stats_max['mean'] + stats_max['std'], 
                 color='red', alpha=0.2, label='Best PDR (±1σ)')

plt.plot(stats_avg['Gen'], stats_avg['mean'], color='blue', marker='s', 
         linestyle='--', linewidth=2, label='Population Avg PDR (Mean)')
plt.fill_between(stats_avg['Gen'], 
                 stats_avg['mean'] - stats_avg['std'], 
                 stats_avg['mean'] + stats_avg['std'], 
                 color='blue', alpha=0.1)

plt.xlabel("Generation", fontsize=12)
plt.ylabel("PDR (%)", fontsize=12)
plt.title(f"Hybrid GA Convergence Robustness ({NUM_RUNS} Independent Runs)", fontsize=14)
plt.legend(loc='lower right', fontsize=10)
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()

plt.savefig("ga_robustness_errorbar.png", dpi=300)
print("\n=> 'ga_robustness_errorbar.png' 논문용 신뢰도 그래프 저장 완료!")
