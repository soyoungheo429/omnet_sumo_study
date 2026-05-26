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
# 5. 메인 루프: 진화 시작
# =========================================================
# random.seed(42) 

print("\n" + "="*60)
print(f"[Hybrid GA] 연속 공간 유전 알고리즘 최적화 시작!")
print(f"인구 수: {POP_SIZE}, 최대 세대: {MAX_GENERATIONS}")
print("="*60)

population = [{'x': random.uniform(0, WIDTH), 'y': random.uniform(0, HEIGHT), 'pdr': 0.0} for _ in range(POP_SIZE)]

history = []
global_best_pdr = -1.0
global_best_x, global_best_y = 0.0, 0.0

for gen in range(1, MAX_GENERATIONS + 1):
    print(f"\n▶ [Generation {gen}/{MAX_GENERATIONS}] 적합도 평가 중...")
    
    # [평가]
    for i, ind in enumerate(population):
        # pdr이 -1.0(에러)이거나 0.0이면 다시 시뮬레이션 (단, 이미 평가된 적이 있는 개체는 skip 가능하지만 GA 특성상 매번 평가가 나을수도 있음)
        # 여기서는 pdr이 0.0인 초기화 상태일 때만 평가하도록 함
        if ind['pdr'] <= 0.0:
            ind['pdr'] = run_simulation(ind['x'], ind['y'])
            if ind['pdr'] < 0: ind['pdr'] = 0.0 # 에러 시 0점으로 처리
        
        if ind['pdr'] > global_best_pdr:
            global_best_pdr, global_best_x, global_best_y = ind['pdr'], ind['x'], ind['y']
            
        lon, lat = utm_proj(ind['x'] + OFFSET_X, ind['y'] + OFFSET_Y, inverse=True)
        history.append({
            "Gen": gen, "Ind_ID": i+1, "X": ind['x'], "Y": ind['y'], 
            "Lat": lat, "Lon": lon, "PDR": ind['pdr'], "IsBest": (ind['pdr'] == global_best_pdr)
        })
        
    population.sort(key=lambda item: item['pdr'], reverse=True)
    print(f"세대 1등: {population[0]['pdr']:.2f}% | 세대 평균: {sum(ind['pdr'] for ind in population) / POP_SIZE:.2f}%")
    
    if gen == MAX_GENERATIONS: break
        
    # [진화]
    next_population = []
    
    # 1. 엘리트 보존
    for i in range(ELITISM_COUNT):
        next_population.append(population[i].copy())
        
    # 2. 교차 & 돌연변이로 자식 생성
    while len(next_population) < POP_SIZE:
        p1 = tournament_selection(population)
        p2 = tournament_selection(population)
        
        c_x, c_y = crossover_and_mutate(p1, p2, gen)
        next_population.append({'x': c_x, 'y': c_y, 'pdr': 0.0})
        
    population = next_population

# 결과 저장 및 시각화
df = pd.DataFrame(history)
df.to_csv(FINAL_CSV, index=False)

print("\n" + "★"*60)
print(f"GA 진화 완료! 최종 명당: X={global_best_x:.2f}, Y={global_best_y:.2f} (PDR: {global_best_pdr:.2f}%)")
print("★"*60)

# 시각화 1. Convergence Plot
plt.figure(figsize=(10, 5))
gen_stats = df.groupby('Gen')['PDR'].agg(['max', 'mean']).reset_index()
plt.plot(gen_stats['Gen'], gen_stats['max'], marker='*', color='r', label='Max PDR per Gen')
plt.plot(gen_stats['Gen'], gen_stats['mean'], marker='o', color='b', linestyle='--', label='Average PDR per Gen')
plt.xlabel("Generation")
plt.ylabel("PDR (%)")
plt.title("Hybrid GA Convergence (Max vs Average)")
plt.legend()
plt.grid(True)
plt.savefig("ga_hybrid_convergence.png")

# 시각화 2. Folium 지도 
best_lon, best_lat = utm_proj(global_best_x + OFFSET_X, global_best_y + OFFSET_Y, inverse=True)
m = folium.Map(location=[best_lat, best_lon], zoom_start=14, tiles='CartoDB Positron')

def get_color(gen):
    # 세대가 지날수록 색상이 변하도록 설정 (Blue -> Purple -> Red)
    colors = ['#3498db', '#9b59b6', '#e74c3c']
    idx = min(len(colors)-1, int((gen-1) / (MAX_GENERATIONS/len(colors))))
    return colors[idx]

for _, row in df.iterrows():
    folium.CircleMarker(
        location=[row["Lat"], row["Lon"]], radius=4 if row["IsBest"] else 2,
        color=get_color(row["Gen"]) if not row["IsBest"] else "orange",
        fill=True, fill_opacity=0.6, popup=f"Gen {row['Gen']} / PDR: {row['PDR']:.2f}%"
    ).add_to(m)

# 최종 승리 명당 
folium.Marker(
    location=[best_lat, best_lon], 
    popup=f"<b>GA Global Best</b><br>PDR: {global_best_pdr:.2f}%", 
    icon=folium.Icon(color='orange', icon='star')
).add_to(m)

folium.Circle(
    location=[best_lat, best_lon], radius=150, color="orange", weight=2, fill=True, fill_opacity=0.1
).add_to(m)

m.save("ga_hybrid_map.html")
print("=> 'ga_hybrid_convergence.png' 및 'ga_hybrid_map.html' 저장 완료!")
