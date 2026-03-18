import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
from pyproj import Transformer

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "rsu_pdr_optimization_results.csv"
SIM_TIME = 200

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
transformer = Transformer.from_crs("epsg:4326", proj_str, always_xy=True)

rsu_locations = [
    {"id": "cluster_15159499_18038479_21113262_347787163_8851291", "lat": 49.576082, "lon": 11.015880},
    {"id": "cluster_12247700_12529558", "lat": 49.577650, "lon": 11.004480},
    {"id": "cluster_347349857_347349858", "lat": 49.576618, "lon": 11.001708},
    {"id": "26841354", "lat": 49.578178, "lon": 11.023730},
    {"id": "17574061", "lat": 49.579060, "lon": 11.020083},
    {"id": "348243041", "lat": 49.577885, "lon": 11.016468},
    {"id": "16933971", "lat": 49.581182, "lon": 11.010784},
    {"id": "19755457", "lat": 49.577864, "lon": 11.007987},
    {"id": "12247702", "lat": 49.580866, "lon": 11.005721},
    {"id": "14319161", "lat": 49.572468, "lon": 11.000520},
    {"id": "19769114", "lat": 49.570403, "lon": 11.000071},
    {"id": "cluster_314448309_824235741", "lat": 49.574876, "lon": 11.009275},
    {"id": "89119479", "lat": 49.574731, "lon": 11.024936},
    {"id": "21970003", "lat": 49.573616, "lon": 11.016800},
    {"id": "17574097", "lat": 49.580694, "lon": 11.024158},
    {"id": "26841336", "lat": 49.578340, "lon": 11.027198},
    {"id": "1154372516", "lat": 49.573137, "lon": 11.030161},
    {"id": "26841358", "lat": 49.575516, "lon": 11.027625},
    {"id": "12452103", "lat": 49.568920, "lon": 11.031449},
    {"id": "1391319738", "lat": 49.576396, "lon": 11.012981},
    {"id": "19755421", "lat": 49.581721, "lon": 11.017490},
    {"id": "21970024", "lat": 49.572838, "lon": 11.019429},
    {"id": "252726522", "lat": 49.569565, "lon": 11.027230},
    {"id": "26841333", "lat": 49.581650, "lon": 11.033591},
    {"id": "314448358", "lat": 49.573159, "lon": 11.007889},
    {"id": "354910587", "lat": 49.569281, "lon": 11.003777},
    {"id": "cluster_1291385696_21971288", "lat": 49.574719, "lon": 11.031625}
]

def run_simulation(loc_id, sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    content = content.replace("RSU_X_PLACEHOLDER", f"{sim_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{sim_y:.2f}")
    
    with open(WORKING_INI, "w") as f:
        f.write(content)
    
    print(f" >>> [ID: {loc_id}] OMNeT++ 좌표 ({sim_x:.2f}, {sim_y:.2f}) 시뮬레이션 진행 중...")
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                            capture_output=True, text=True)
    return process.returncode

def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    total_received = 0
    rsu_generated = 0
    node_count = 0

    if not os.path.exists(result_path): return 0

    try:
        with open(result_path, "r") as f:
            content = f.read()

            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match: rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            for val in node_recv_matches:
                total_received += int(val)
                node_count += 1

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles

        if expected_total == 0: return 0

        pdr = (total_received / expected_total) * 100
        print(f"      => 결과: RSU발신({rsu_generated}) * 차량({num_vehicles}대) | 수신총합({total_received}) -> PDR: {pdr:.2f}%\n")
        return pdr
    except Exception as e:
        print(f"파싱 에러: {e}")
        return 0

final_data = []
print("[위경도 -> 시뮬레이션 좌표 자동 변환] RSU 최적 위치 탐색 시작\n")

for loc in rsu_locations:
    utm_x, utm_y = transformer.transform(loc["lon"], loc["lat"])
    
    sim_x = utm_x - OFFSET_X + 50
    sim_y = utm_y - OFFSET_Y - 300
    
    run_simulation(loc["id"], sim_x, sim_y)
    pdr = parse_pdr()
    
    final_data.append({
        "ID": loc["id"], 
        "Lat": loc["lat"], 
        "Lon": loc["lon"], 
        "Sim_X": sim_x,  
        "Sim_Y": sim_y,   
        "PDR": pdr
    })

df = pd.DataFrame(final_data)
df.to_csv(FINAL_CSV, index=False)

plt.figure(figsize=(15, 7))
df_sorted = df.sort_values(by="PDR", ascending=False)
bars = plt.bar([str(i) for i in df_sorted["ID"]], df_sorted["PDR"], color='forestgreen')
if len(bars) > 0:
    bars[0].set_color('orange')

plt.xlabel("RSU ID (Location)")
plt.ylabel("Broadcast PDR (%)")
plt.title("Filtered RSU Placement Optimization (BSM Delivery Ratio)")
plt.xticks(rotation=90)
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.tight_layout()
plt.savefig("pdr_results.png")

print(f"총 {len(rsu_locations)}개 교차로 평가 완료. 결과 파일: {FINAL_CSV}")
