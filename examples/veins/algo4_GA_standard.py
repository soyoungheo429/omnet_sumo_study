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
FINAL_CSV = "algo4_ga_results.csv"

# 에를랑겐 맵 설정 (기존 알고리즘과 동일)
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73

# 좌표 변환 설정
proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# 2. GA 파라미터
POP_SIZE = 9        # 초기 인구수 (사용자 요청: 9개 점)
GEN_MAX = 5         # 최대 세대 수 (테스트를 위해 작게 설정)
MUTATION_RATE = 0.2
CROSSOVER_RATE = 0.8

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
    if not os.path.exists(result_path): return 0.0

    try:
        total_received = 0
        rsu_generated = 0
        node_count = 0
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

# 4. 초기 인구 생성 (특정 Edge의 9개 점)
def generate_initial_population():
    # 에를랑겐 맵의 특정 Edge (id: 4319352#1)의 형상 데이터를 기반으로 9개 점 선정
    # 이 좌표들은 SUMO 절대 좌표이며, OFFSET을 빼서 시뮬레이션 좌표로 변환해야 함
    edge_shape = [
        (644909.66, 5493593.74), (644918.42, 5493589.42), (644967.49, 5493565.92),
        (644996.86, 5493554.99), (645048.18, 5493536.80), (645085.26, 5493525.56),
        (645130.08, 5493513.21), (645188.80, 5493499.81), (645239.38, 5493491.34),
        (645277.77, 5493487.84), (645289.29, 5493486.63), (645307.62, 5493484.97),
        (645348.32, 5493482.58), (645398.23, 5493478.81), (645555.88, 5493464.89)
    ]
    
    # 15개 중 균등하게 9개 선정
    selected_indices = [int(i * (len(edge_shape) - 1) / (POP_SIZE - 1)) for i in range(POP_SIZE)]
    
    population = []
    for idx in selected_indices:
        abs_x, abs_y = edge_shape[idx]
        # algo1 방식: sim_x = utm_x - OFFSET_X + 50
        x = abs_x - OFFSET_X 
        y = abs_y - OFFSET_Y 
        population.append({'x': x, 'y': y, 'pdr': -1.0})
    
    print(f"초기 부모 9개 점 선정 완료 (Edge id: 4319352#1 기반)")
    return population

# 5. GA 연산: Weighted Crossover & Geometric Variation
def weighted_crossover(p1, p2):
    # PDR 점수가 높을수록 더 많은 가중치를 부여하여 자식 생성
    total_pdr = p1['pdr'] + p2['pdr']
    if total_pdr <= 0:
        w1, w2 = 0.5, 0.5
    else:
        # PDR에 비례한 가중치 (더 좋은 부모에 가깝게)
        w1 = p1['pdr'] / total_pdr
        w2 = p2['pdr'] / total_pdr
    
    # 가중 평균 (Weighted Sum)
    child_x = p1['x'] * w1 + p2['x'] * w2
    child_y = p1['y'] * w1 + p2['y'] * w2
    
    # [사각형에 갖히는 문제 해결]
    # 단순히 부모 사이의 내분점만 찾으면 검색 범위가 좁아지므로,
    # 일정 확률로 외분(Extrapolation)을 허용하거나 기하적 변동을 줍니다.
    if random.random() < 0.3:
        # 외분점 (부모 1 방향으로 더 나감)
        ext_factor = random.uniform(1.1, 1.3)
        child_x = p2['x'] + (p1['x'] - p2['x']) * ext_factor
        child_y = p2['y'] + (p1['y'] - p2['y']) * ext_factor
        
    return {'x': child_x, 'y': child_y, 'pdr': -1.0}

def mutate(ind):
    # 돌연변이: 기하적 특성을 고려하여 현재 위치에서 주변으로 무작위 이동
    if random.random() < MUTATION_RATE:
        # STEP_SIZE를 Simulated Annealing처럼 활용하거나 고정값 사용
        move_dist = random.uniform(50, 200)
        angle = random.uniform(0, 2 * math.pi)
        ind['x'] = max(0, min(WIDTH, ind['x'] + move_dist * math.cos(angle)))
        ind['y'] = max(0, min(HEIGHT, ind['y'] + move_dist * math.sin(angle)))
    return ind

# 6. 메인 GA 루프
def run_ga():
    print("🚀 Genetic Algorithm 시작...")
    population = generate_initial_population()
    history = []
    
    best_ind = None

    for gen in range(GEN_MAX):
        print(f"\n--- 세대 {gen+1} ---")
        
        # 1. 적합도 평가
        for i, ind in enumerate(population):
            if ind['pdr'] < 0: # 아직 평가되지 않은 경우만 시뮬레이션
                print(f"  [Ind {i+1}/{POP_SIZE}] 위치 ({ind['x']:.1f}, {ind['y']:.1f}) 평가 중...", end="")
                ind['pdr'] = run_simulation(ind['x'], ind['y'])
                print(f" PDR: {ind['pdr']:.2f}%")
            
            if best_ind is None or ind['pdr'] > best_ind['pdr']:
                best_ind = ind.copy()
            
            # 기록 저장
            lon, lat = utm_proj(ind['x'] + OFFSET_X, ind['y'] + OFFSET_Y, inverse=True)
            history.append({
                "Generation": gen,
                "X": ind['x'],
                "Y": ind['y'],
                "Lat": lat,
                "Lon": lon,
                "PDR": ind['pdr']
            })

        # 2. 선택 및 교차 (다음 세대 생성)
        new_population = [best_ind.copy()] # Elitism: 최고 개체는 보존
        
        while len(new_population) < POP_SIZE:
            # Roulette Wheel Selection (PDR 기준)
            parents = random.choices(population, weights=[max(0.1, p['pdr']) for p in population], k=2)
            
            if random.random() < CROSSOVER_RATE:
                child = weighted_crossover(parents[0], parents[1])
            else:
                child = random.choice(parents).copy()
                child['pdr'] = -1.0 # 다시 평가해야 함
            
            child = mutate(child)
            new_population.append(child)
        
        population = new_population

    return best_ind, history

# 7. 실행 및 결과 저장
random.seed(42)
best_rsu, history = run_ga()

df = pd.DataFrame(history)
df.to_csv(FINAL_CSV, index=False)

print("\n" + "="*50)
print("GA 최적화 완료!")
print(f"최적 위치: X={best_rsu['x']:.2f}, Y={best_rsu['y']:.2f}")
print(f"최고 PDR: {best_rsu['pdr']:.2f}%")
print("="*50)

# 시각화 및 지도 생성 (기존 algo3 코드 활용)
plt.figure(figsize=(10, 5))
plt.xlabel("Generation")
plt.ylabel("PDR (%)")
plt.title("GA Convergence")
plt.grid(True)
plt.savefig("algo4_ga_convergence.png")

# Folium 지도 (흰색 지도 스타일: CartoDB Positron)
m = folium.Map(location=[df["Lat"].mean(), df["Lon"].mean()], zoom_start=14, tiles='CartoDB Positron')

# 모든 시도 지점을 작게 표시 (세대별 흐름 파악용)
for idx, row in df.iterrows():
    folium.CircleMarker(
        location=[row["Lat"], row["Lon"]],
        radius=2,
        color="gray",
        fill=True,
        fill_opacity=0.3,
        popup=f"Gen {row['Generation']}: {row['PDR']:.2f}%"
    ).add_to(m)

# 최종 최적 위치 (1등 별표 마킹)
best_lon, best_lat = utm_proj(best_rsu['x'] + OFFSET_X, best_rsu['y'] + OFFSET_Y, inverse=True)
folium.Marker(
    location=[best_lat, best_lon],
    popup=f"<b>GA Best</b><br>PDR: {best_rsu['pdr']:.2f}%",
    icon=folium.Icon(color='orange', icon='star')
).add_to(m)

# 150m 통신 반경 시각화
folium.Circle(
    location=[best_lat, best_lon],
    radius=150,
    color="orange",
    weight=2,
    fill=True,
    fill_opacity=0.2
).add_to(m)

m.save("algo4_ga_map.html")
print("=> 'algo4_ga_convergence.png' 및 'algo4_ga_map.html' (CartoDB Positron 스타일) 저장 완료")

