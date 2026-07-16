import os
import subprocess
import pandas as pd
import itertools
import re
import shutil

# =========================================================
# 1. 설정값
# =========================================================
ALGO1_RESULT_CSV = "rsu_pdr_optimization_results_40.csv" # 단일 RSU 1등~꼴등 결과 파일
TOP_N = 40        # 상위 40개 교차로 추출
K_RSUS = 2        # K=2 (조합할 RSU 개수)

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "baseline_40c2_results_40.csv"

# =========================================================
# 2. 상위 40개 교차로 로드 및 780개 조합 생성
# =========================================================
if not os.path.exists(ALGO1_RESULT_CSV):
    print(f"오류: {ALGO1_RESULT_CSV} 파일이 없습니다.")
    exit()

# 단일 RSU 결과에서 PDR 기준 내림차순 정렬 후 상위 40개 추출
df_single = pd.read_csv(ALGO1_RESULT_CSV)
df_top40 = df_single.sort_values(by='PDR', ascending=False).head(TOP_N)

# 교차로 ID와 좌표를 리스트로 변환
candidates = []
for idx, row in df_top40.iterrows():
    # 'ID' 컬럼이 없다면 인덱스를 사용
    node_id = row['ID'] if 'ID' in row else f"Node_{idx}"
    candidates.append({
        'id': node_id,
        'x': row['Sim_X'],
        'y': row['Sim_Y'],
        'single_pdr': row['PDR']
    })

# 40개 중 2개를 고르는 모든 조합 (40C2 = 780개) 생성
combinations_780 = list(itertools.combinations(candidates, K_RSUS))

print("="*60)
print(f"상위 {TOP_N}개 교차로 로드 완료 (단일 PDR {df_top40['PDR'].min():.2f}% ~ {df_top40['PDR'].max():.2f}%)")
print(f"총 {len(combinations_780)}개의 시뮬레이션(조합)을 실행합니다.")
print("="*60)

# =========================================================
# 3. 시뮬레이션 및 파싱 함수
# =========================================================
def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path): return 0.0

    try:
        total_received, rsu_generated, node_count = 0, 0, 0
        with open(result_path, "r") as f:
            content = f.read()
            
            # K개의 RSU가 생성한 BSM 모두 합산
            rsu_gen_matches = re.findall(r"rsu\[\d+\].appl\s+generatedBSMs\s+(\d+)", content)
            rsu_generated = sum(int(val) for val in rsu_gen_matches)
            
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

def run_simulation(rsu1, rsu2):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    # 템플릿의 RSU 관련 설정 덮어쓰기 (Z축 포함)
    multi_rsu_config = f"\n\n# --- Baseline {K_RSUS}개 RSU 자동 생성 ---\n"
    multi_rsu_config += f"*.numRSUs = {K_RSUS}\n"
    
    multi_rsu_config += f"*.rsu[0].mobility.x = {rsu1['x']:.2f}\n"
    multi_rsu_config += f"*.rsu[0].mobility.y = {rsu1['y']:.2f}\n"
    multi_rsu_config += f"*.rsu[1].mobility.x = {rsu2['x']:.2f}\n"
    multi_rsu_config += f"*.rsu[1].mobility.y = {rsu2['y']:.2f}\n"
    multi_rsu_config += "*.rsu[*].mobility.z = 3\n"
    
    content = content.replace("[General]", "[General]" + multi_rsu_config)
    
    with open(WORKING_INI, "w") as f:
        f.write(content + multi_rsu_config)
        
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], capture_output=True, text=True)
    
    if process.returncode != 0 or "<!> Error" in process.stderr or "<!> Error" in process.stdout:
        print(f"\n🚨 시뮬레이션 에러 발생! OMNeT++가 이렇게 말했습니다:\n{process.stderr}\n{process.stdout}")
        return 0.0
    return parse_pdr()

# =========================================================
# 4. 780회 메인 루프 실행
# =========================================================
results = []

for idx, (rsu1, rsu2) in enumerate(combinations_780):
    print(f"▶ [{idx+1}/{len(combinations_780)}] 조합 테스트 중... ", end="\r")
    
    combined_pdr = run_simulation(rsu1, rsu2)
    
    results.append({
        'Combo_ID': f"Combo_{idx+1}",
        'RSU1_ID': rsu1['id'],
        'RSU1_X': rsu1['x'],
        'RSU1_Y': rsu1['y'],
        'RSU1_Single_PDR': rsu1['single_pdr'],
        'RSU2_ID': rsu2['id'],
        'RSU2_X': rsu2['x'],
        'RSU2_Y': rsu2['y'],
        'RSU2_Single_PDR': rsu2['single_pdr'],
        'Combined_PDR': combined_pdr
    })
    print(f"▶ [{idx+1}/{len(combinations_780)}] {rsu1['id']} & {rsu2['id']} 조합 -> 통합 PDR: {combined_pdr:.2f}%")

# 결과 저장
df_results = pd.DataFrame(results)
df_results = df_results.sort_values(by='Combined_PDR', ascending=False)
df_results.to_csv(FINAL_CSV, index=False)

print("\n" + "="*60)
print(f"780개 조합 테스트 완료! '{FINAL_CSV}'에 저장되었습니다.")
best_combo = df_results.iloc[0]
print(f"1등 조합: {best_combo['RSU1_ID']} & {best_combo['RSU2_ID']} -> PDR {best_combo['Combined_PDR']:.2f}%")
print("="*60)
