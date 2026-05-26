import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import folium
from pyproj import Proj

# 1. 시뮬레이션 및 맵 설정값
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "bruteforce_grid_results.csv"

# 에를랑겐 맵의 정확한 가로/세로 길이 및 오프셋
OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46   # 647071.55 - 644465.09
HEIGHT = 3009.73  # 5494795.98 - 5491786.25
GRID_SIZE = 150.0

# 좌표 변환 (SUMO 미터 좌표 -> GPS 위경도 변환용)
proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

# 2. Grid 정중앙 좌표 생성 함수
def generate_grid_centers(width, height, step):
    candidates = []
    num_x = int(width // step)
    num_y = int(height // step)
    
    cand_id = 1
    for i in range(num_x):
        for j in range(num_y):
		# [수정된 부분] + (step / 2) 를 제거하여 평행이동! (0, 150, 300... 으로 생성)
            rel_x = float(i * step)
            rel_y = float(j * step)
            
            # SUMO 절대 좌표
            sumo_x = rel_x + OFFSET_X
            sumo_y = rel_y + OFFSET_Y
            
            # OMNeT++ 시뮬레이션용 좌표 
            sim_x = rel_x
            sim_y = rel_y
            
            # Folium 지도용 GPS 좌표 (위도, 경도)
            lon, lat = utm_proj(sumo_x, sumo_y, inverse=True)
            
            candidates.append({
                "id": f"Grid_{cand_id}",
                "rel_x": rel_x,
                "rel_y": rel_y,
                "sim_x": sim_x,
                "sim_y": sim_y,
                "lat": lat,
                "lon": lon
            })
            cand_id += 1
            
    return candidates

# 3. OMNeT++ 시뮬레이션 실행 및 에러 감지 함수
def run_simulation(loc_id, sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    # ini 파일에 좌표 주입
    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    content = content.replace("RSU_X_PLACEHOLDER", f"{sim_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{sim_y:.2f}")
    with open(WORKING_INI, "w") as f:
        f.write(content)
    
    # 프로세스 실행 (Cmdenv 모드)
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
    
    # -에러 감지 로직 
    is_success = True
    error_msg = ""

    if process.returncode != 0:
        is_success = False
        error_msg = f"Crash (Code: {process.returncode})"
    elif "<!> Error" in process.stdout or "<!> Error" in process.stderr:
        is_success = False
        error_msg = "Internal Error (<!> Error detected)"
        
    return is_success, error_msg, process.stdout

# 4. PDR 파싱 함수 
def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    total_received = 0
    rsu_generated = 0

    if not os.path.exists(result_path): 
        return 0.0

    try:
        with open(result_path, "r") as f:
            content = f.read()
            
            # RSU가 생성한 BSM 개수 파싱
            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match: 
                rsu_generated = int(rsu_gen_match.group(1))
            
            # 각 차량이 수신한 BSM 개수 파싱 후 합산
            node_recv_matches = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            for val in node_recv_matches:
                total_received += int(val)

        # PDR 공식 적용
        num_vehicles = 50
        expected_total = rsu_generated * num_vehicles
        
        if expected_total == 0: 
            return 0.0
        
        pdr = (total_received / expected_total) * 100
        return pdr
    except Exception as e:
        print(f"\n파싱 에러: {e}")
        return 0.0

# 5. 메인 Brute-force 실행 루프
print("\n" + "="*50)
print(f" [전역 탐색 시작] 구역: {WIDTH}m x {HEIGHT}m, 해상도: {GRID_SIZE}m")
print("="*50)

candidates = generate_grid_centers(WIDTH, HEIGHT, GRID_SIZE)
print(f"총 {len(candidates)}개의 Grid 중심 좌표가 생성되었습니다.\n")

final_data = []

for idx, cand in enumerate(candidates):
    print(f"[{idx+1}/{len(candidates)}] {cand['id']} (X:{cand['sim_x']:.1f}, Y:{cand['sim_y']:.1f})...", end="")
    
    # 시뮬레이션 돌리기 및 에러 확인
    is_success, error_msg, full_log = run_simulation(cand["id"], cand["sim_x"], cand["sim_y"])
    
    if is_success:
        pdr = parse_pdr()
        print(f" => 정상 완주! (PDR: {pdr:.2f}%)")
    else:
        pdr = -1.0  # 에러 표식
        print(f" [에러 발생] {error_msg}")

    # 리스트에 데이터 추가
    final_data.append({
        "ID": cand["id"],
        "Rel_X": cand["rel_x"],
        "Rel_Y": cand["rel_y"],
        "Lat": cand["lat"],
        "Lon": cand["lon"],
        "PDR": pdr
    })

# 6. 결과 저장 및 시각화
df = pd.DataFrame(final_data)
df.to_csv(FINAL_CSV, index=False)

# 에러(-1.0) 제외하고 최고 성능 찾기
df_valid = df[df["PDR"] >= 0]

if not df_valid.empty:
    df_sorted = df_valid.sort_values(by="PDR", ascending=False).reset_index(drop=True)
    best_rsu = df_sorted.iloc[0]

    print("\n" + "="*50)
    print("Brute-force 탐색 완료!")
    print(f"최고 성능 RSU: {best_rsu['ID']} (Lat: {best_rsu['Lat']:.6f}, Lon: {best_rsu['Lon']:.6f})")
    print(f"달성 PDR: {best_rsu['PDR']:.2f}%")
    print("="*50)

    # Matplotlib 산점도 (Heatmap 스타일)
    plt.figure(figsize=(10, 10))
    # PDR 0 이상인 정상 데이터만 시각화
    sc = plt.scatter(df_valid["Rel_X"], df_valid["Rel_Y"], c=df_valid["PDR"], cmap='RdYlGn', alpha=0.8, s=100, edgecolors='k')
    plt.colorbar(sc, label='Packet Delivery Ratio (PDR %)')
    
    # 에러가 난 곳은 검은색 X 표시
    df_error = df[df["PDR"] == -1.0]
    if not df_error.empty:
        plt.scatter(df_error["Rel_X"], df_error["Rel_Y"], color='black', marker='x', s=50, label='Error / Crash')

    plt.scatter(best_rsu["Rel_X"], best_rsu["Rel_Y"], color='blue', marker='*', s=300, label=f'Best: {best_rsu["PDR"]:.1f}%')

    plt.xlim(0, WIDTH)
    plt.ylim(0, HEIGHT)
    plt.title("Grid-based Global Search PDR Heatmap")
    plt.xlabel("X Coordinate (m)")
    plt.ylabel("Y Coordinate (m)")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.savefig("bruteforce_heatmap.png")
    print("=> 'bruteforce_heatmap.png' 저장 완료")

    # Folium 인터랙티브 맵 저장
    center_lat = df_valid["Lat"].mean()
    center_lon = df_valid["Lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles='CartoDB Positron')

    for idx, row in df.iterrows():
        lat, lon, pdr_val = row["Lat"], row["Lon"], row["PDR"]
        
        if pdr_val == -1.0:
            color, radius_op, border = "black", 0.8, 1
            label = "ERROR"
        elif pdr_val == best_rsu["PDR"]:
            color, radius_op, border = "blue", 0.5, 3
            label = f"BEST (PDR: {pdr_val:.1f}%)"
        elif pdr_val >= 80:
            color, radius_op, border = "green", 0.3, 1
            label = f"PDR: {pdr_val:.1f}%"
        elif pdr_val >= 50:
            color, radius_op, border = "orange", 0.2, 1
            label = f"PDR: {pdr_val:.1f}%"
        else:
            color, radius_op, border = "red", 0.1, 0
            label = f"PDR: {pdr_val:.1f}%"

        folium.CircleMarker(
            location=[lat, lon],
            radius=5 + border,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=f"<b>{label}</b><br>ID: {row['ID']}"
        ).add_to(m)

        if pdr_val == best_rsu["PDR"]:
            folium.Circle(
                location=[lat, lon],
                radius=150,
                color="blue",
                weight=2,
                fill=True,
                fill_opacity=0.2
            ).add_to(m)

    m.save("bruteforce_interactive_map.html")
    print("=> 'bruteforce_interactive_map.html' 저장 완료\n")
    
else:
    # 모든 시뮬레이션이 에러(-1.0)인 경우 처리
    print("\n모든 시뮬레이션에서 에러가 발생했습니다. 로그를 확인해주세요.")
