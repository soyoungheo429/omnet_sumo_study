import os
import subprocess
import pandas as pd
import shutil
import re
import math
import random
from pyproj import Proj

# =========================================================
# 1. 설정 및 초기화
# =========================================================
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "best_rsu_candidates.csv" # 최종 상위 후보 저장 파일

# 에를랑겐 맵 설정 (소영님 맵 기준 보정치 적용)
OFFSET_X = 644515.09
OFFSET_Y = 5491486.25
WIDTH = 2606.46
HEIGHT = 3009.73

# GA 파라미터
POP_SIZE = 10
MAX_GENERATIONS = 10
SEARCH_RADIUS = 150.0 # 탐색 반경
K_TOP = 27             # 상위 K개 추출

# 시작점: 가장 높은 PDR을 보였던 교차로 ID (예시)
START_X, START_Y = 1318.73, 1365.10 

# =========================================================
# 2. 시뮬레이션 함수
# =========================================================
def run_simulation(x, y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    # 설정 주입
    content = content.replace("RSU_X_PLACEHOLDER", f"{x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{y:.2f}")
    content += f"\nseed-set = {random.randint(0, 999999)}\n"
    
    with open(WORKING_INI, "w") as f:
        f.write(content)
        
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
    
    if process.returncode != 0: return 0.0
    return parse_pdr()

def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path): return 0.0
    try:
        with open(result_path, "r") as f:
            content = f.read()
            rsu_gen = int(re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content).group(1))
            nodes = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            total_recv = sum(int(n) for n in nodes)
        return (total_recv / (rsu_gen * (len(nodes) if nodes else 50))) * 100
    except: return 0.0

# =========================================================
# 3. GA 핵심 로직
# =========================================================
def crossover_and_mutate(p1, p2, gen):
    m_x = (p1['x'] + p2['x']) / 2
    m_y = (p1['y'] + p2['y']) / 2
    
    # 적응형 시그마 (세대가 지날수록 좁게 탐색)
    sigma = 150.0 - (145.0 * (gen / MAX_GENERATIONS))
    
    # 여기서 부모의 평균(m_x, m_y)을 기준으로 가우시안 돌연변이 발생!
    c_x = max(0, min(WIDTH, random.gauss(m_x, sigma)))
    c_y = max(0, min(HEIGHT, random.gauss(m_y, sigma))) # ★ c_y -> m_y로 수정
    
    return c_x, c_y

# =========================================================
# 4. 메인 실행
# =========================================================
population = [{'x': START_X + random.uniform(-50,50), 'y': START_Y + random.uniform(-50,50), 'pdr': 0.0} for _ in range(POP_SIZE)]

for gen in range(1, MAX_GENERATIONS + 1):
    print(f"▶ [Gen {gen}] 진화 중...")
    for ind in population:
        if ind['pdr'] == 0.0: ind['pdr'] = run_simulation(ind['x'], ind['y'])
    
    population.sort(key=lambda x: x['pdr'], reverse=True)
    next_pop = [population[0].copy()]
    while len(next_pop) < POP_SIZE:
        p1, p2 = random.sample(population[:5], 2)
        cx, cy = crossover_and_mutate(p1, p2, gen)
        next_pop.append({'x': cx, 'y': cy, 'pdr': 0.0})
    population = next_pop

# 최종 저장
df = pd.DataFrame(population).sort_values(by='pdr', ascending=False)
df.head(K_TOP).to_csv(FINAL_CSV, index=False)
print(f"\n최종 완료! 상위 {K_TOP}개 결과가 '{FINAL_CSV}'에 저장되었습니다.")

print("\n--- [환경 검증 시작] ---")
test_pdr = run_simulation(1318.73, 1365.10) 
print(f"좌표 (1318.73, 1365.10) 검증 결과: {test_pdr:.2f}%")
