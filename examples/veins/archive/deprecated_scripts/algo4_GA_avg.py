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
FINAL_CSV = "ga_hybrid_final_results.csv"

# 에를랑겐 맵 설정
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

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
MIN_SIGMA = 5.0           # 5m (막판 건물 모퉁이 미세 조정)

# =========================================================
# 3. OMNeT++ 시뮬레이션 및 적합도(PDR) 평가 함수
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
# 4. GA 핵심 연산자: 하이브리드 교차 및 돌연변이
# =========================================================
def tournament_selection(population):
    """토너먼트 선택: 무작위 3명 중 1등(부모) 선발"""
    competitors = random.sample(population, 3)
    competitors.sort(key=lambda ind: ind['pdr'], reverse=True)
    return competitors[0]

def crossover_and_mutate(parent1, parent2, current_gen):
    """가중 평균 교차 + 적응형 가우시안 돌연변이 결합"""
    
    # 1. PDR 가중합을 통한 기본 중심점(m) 계산
    total_pdr = parent1['pdr'] + parent2['pdr']
    if total_pdr <= 0:
        w1, w2 = 0.5, 0.5
    else:
        w1 = parent1['pdr'] / total_pdr
        w2 = parent2['pdr'] / total_pdr
        
    m_x = (parent1['x'] * w1) + (parent2['x'] * w2)
    m_y = (parent1['y'] * w1) + (parent2['y'] * w2)
    
    # 2. 시간에 따른 적응형 σ 계산 (점점 좁아짐)
    ratio = current_gen / MAX_GENERATIONS
    current_sigma = MAX_SIGMA - (MAX_SIGMA - MIN_SIGMA) * ratio
    
    # 3. 가우시안 돌연변이 (m 좌표를 평균으로 삼아 폭발)
    child_x = random.gauss(m_x, current_sigma)
    child_y = random.gauss(m_y, current_sigma)
    
    # 4. 맵 경계선 crop
    child_x = max(0, min(WIDTH, child_x))
    child_y = max(0, min(HEIGHT, child_y))
    
    return child_x, child_y

# =========================================================
# 5. 메인 루프: 다중 실행(Multi-Run) 알고리즘 안정성 검증
# =========================================================
NUM_RUNS = 15  # 알고리즘을 완전히 새롭게 30번 반복 실행합니다.

print("\n" + "="*60)
print(f"[Robustness Test] GA {NUM_RUNS}회 독립 실행 시작!")
print("="*60)

all_runs_history = []

for run_idx in range(1, NUM_RUNS + 1):
    print(f"\n" + "▼"*40)
    print(f"  실행 회차: [ RUN {run_idx} / {NUM_RUNS} ] 시작")
    print("▼"*40)
    
    # 이 회차(Run)만의 전역 최고 기록 초기화
    run_best_pdr = -1.0
    
    # 1. 초기 개체군 생성 (매 Run마다 완전히 새로운 무작위 위치에서 시작)
    population = [{'x': random.uniform(0, WIDTH), 'y': random.uniform(0, HEIGHT), 'pdr': 0.0} for _ in range(POP_SIZE)]

    for gen in range(1, MAX_GENERATIONS + 1):
        print(f"▶ Run {run_idx} - [Gen {gen}/{MAX_GENERATIONS}] 평가 중...", end="\r")
        
        # [평가]
        for i, ind in enumerate(population):
            if ind['pdr'] == 0.0:
                ind['pdr'] = run_simulation(ind['x'], ind['y'])
            
            if ind['pdr'] > run_best_pdr:
                run_best_pdr = ind['pdr']
                
        # 현재 세대의 최고 PDR 찾기 (그래프용)
        population.sort(key=lambda item: item['pdr'], reverse=True)
        gen_max_pdr = population[0]['pdr']
        gen_avg_pdr = sum(ind['pdr'] for ind in population) / POP_SIZE
        
        # 데이터 기록 (Run 번호 추가!)
        all_runs_history.append({
            "Run": run_idx,
            "Gen": gen,
            "Max_PDR": gen_max_pdr,
            "Avg_PDR": gen_avg_pdr
        })
        
        if gen == MAX_GENERATIONS: break
            
        # [진화]
        next_population = []
        for i in range(ELITISM_COUNT): # 엘리트 보존
            next_population.append(population[i].copy())
            
        while len(next_population) < POP_SIZE: # 교차 & 돌연변이
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
df.to_csv("ga_multirun_results.csv", index=False)

# 1. 세대별 통계 계산 (각 세대마다 5번의 Run 결과를 모아 평균과 표준편차 도출)
# "최고 PDR(Max_PDR)"의 통계
stats_max = df.groupby('Gen')['Max_PDR'].agg(['mean', 'std']).reset_index()
# "평균 PDR(Avg_PDR)"의 통계
stats_avg = df.groupby('Gen')['Avg_PDR'].agg(['mean', 'std']).reset_index()

plt.figure(figsize=(10, 6))

# 2. 세대별 '최고 PDR' 평균선 및 에러 음영 (빨간색)
plt.plot(stats_max['Gen'], stats_max['mean'], color='red', marker='o', 
         linestyle='-', linewidth=2, label='Generation Best PDR (Mean)')
plt.fill_between(stats_max['Gen'], 
                 stats_max['mean'] - stats_max['std'], 
                 stats_max['mean'] + stats_max['std'], 
                 color='red', alpha=0.2, label='Best PDR (±1σ)')

# 3. 세대별 '평균 PDR' 평균선 및 에러 음영 (파란색)
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
