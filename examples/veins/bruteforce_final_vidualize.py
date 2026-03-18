import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import folium

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "rsu_pdr_optimization_results.csv"
SIM_TIME = 200

rsu_data = [
    {"id": "cluster_15159499_18038479_21113262_347787163_8851291", "x": 1318.75, "y": 1365.05, "lat": 49.576082, "lon": 11.015880},
    {"id": "cluster_12247700_12529558", "x": 490.02, "y": 1517.34, "lat": 49.577650, "lon": 11.004480},
    {"id": "cluster_347349857_347349858", "x": 292.64, "y": 1397.32, "lat": 49.576618, "lon": 11.001708},
    {"id": "26841354", "x": 1879.94, "y": 1613.33, "lat": 49.578178, "lon": 11.023730},
    {"id": "17574061", "x": 1613.70, "y": 1704.30, "lat": 49.579060, "lon": 11.020083},
    {"id": "348243041", "x": 1355.88, "y": 1566.67, "lat": 49.577885, "lon": 11.016468},
    {"id": "16933971", "x": 935.22, "y": 1922.14, "lat": 49.581182, "lon": 11.010784},
    {"id": "17573721", "x": 764.28, "y": 1897.69, "lat": 49.581003, "lon": 11.008412},
    {"id": "19755457", "x": 742.84, "y": 1547.94, "lat": 49.577864, "lon": 11.007987},
    {"id": "12247702", "x": 570.19, "y": 1877.31, "lat": 49.580866, "lon": 11.005721},
    {"id": "14319161", "x": 219.06, "y": 933.73, "lat": 49.572468, "lon": 11.000520},
    {"id": "19769114", "x": 192.71, "y": 703.26, "lat": 49.570403, "lon": 11.000071},
    {"id": "cluster_314448309_824235741", "x": 844.81, "y": 1218.29, "lat": 49.574876, "lon": 11.009275},
    {"id": "21969082", "x": 933.37, "y": 1527.64, "lat": 49.577636, "lon": 11.010613},
    {"id": "89119479", "x": 1977.38, "y": 1232.46, "lat": 49.574731, "lon": 11.024936},
    {"id": "17574090", "x": 1992.64, "y": 1752.05, "lat": 49.579398, "lon": 11.025340},
    {"id": "26841356", "x": 1766.29, "y": 1462.92, "lat": 49.576853, "lon": 11.022103},
    {"id": "21970003", "x": 1392.57, "y": 1092.77, "lat": 49.573616, "lon": 11.016800},
    {"id": "17574097", "x": 1903.32, "y": 1893.85, "lat": 49.580694, "lon": 11.024158},
    {"id": "26841336", "x": 2130.14, "y": 1638.05, "lat": 49.578340, "lon": 11.027198},
    {"id": "17574059", "x": 1623.51, "y": 1903.04, "lat": 49.580844, "lon": 11.020293},
    {"id": "347349917", "x": 205.82, "y": 1547.75, "lat": 49.577991, "lon": 11.000563},
    {"id": "1154372516", "x": 2359.88, "y": 1065.53, "lat": 49.573137, "lon": 11.030161},
    {"id": "13493753", "x": 540.79, "y": 1663.62, "lat": 49.578952, "lon": 11.005236},
    {"id": "15420062", "x": 1079.42, "y": 2001.76, "lat": 49.581863, "lon": 11.012807},
    {"id": "19755477", "x": 872.93, "y": 1768.10, "lat": 49.579812, "lon": 11.009866},
    {"id": "21262677", "x": 839.11, "y": 2088.17, "lat": 49.582697, "lon": 11.009517},
    {"id": "26841358", "x": 2169.45, "y": 1325.02, "lat": 49.575516, "lon": 11.027625},
    {"id": "14319163", "x": 385.45, "y": 1226.37, "lat": 49.575059, "lon": 11.002928},
    {"id": "12452103", "x": 2465.71, "y": 599.22, "lat": 49.568920, "lon": 11.031449},
    {"id": "1391319738", "x": 1108.25, "y": 1394.45, "lat": 49.576396, "lon": 11.012981},
    {"id": "16933976", "x": 1087.34, "y": 1550.95, "lat": 49.577808, "lon": 11.012750},
    {"id": "19755421", "x": 1418.33, "y": 1995.04, "lat": 49.581721, "lon": 11.017490},
    {"id": "21970024", "x": 1584.98, "y": 1011.38, "lat": 49.572838, "lon": 11.019429},
    {"id": "252726522", "x": 2158.70, "y": 662.71, "lat": 49.569565, "lon": 11.027230},
    {"id": "26841333", "x": 2582.32, "y": 2018.54, "lat": 49.581650, "lon": 11.033591},
    {"id": "314448358", "x": 749.71, "y": 1024.75, "lat": 49.573159, "lon": 11.007889},
    {"id": "354910587", "x": 463.96, "y": 585.69, "lat": 49.569281, "lon": 11.003777},
    {"id": "39537846", "x": 2084.76, "y": 822.95, "lat": 49.571024, "lon": 11.026267},
    {"id": "cluster_1291385696_21971288", "x": 2460.97, "y": 1244.22, "lat": 49.574719, "lon": 11.031625}
]

def run_simulation(loc_index, x, y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    
    content = content.replace("RSU_X_PLACEHOLDER", f"{x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{y:.2f}")
    
    with open(WORKING_INI, "w") as f:
        f.write(content)
    
    print(f" >>> [ID: {loc_index}] 위치 시뮬레이션 진행 중...")
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
            if rsu_gen_match:
                rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            for val in node_recv_matches:
                total_received += int(val)
                node_count += 1

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles

        if expected_total == 0: return 0

        pdr = (total_received / expected_total) * 100
        print(f"      => 결과: 수신총합({total_received}) -> PDR: {pdr:.2f}%\n")
        return pdr
    except Exception as e:
        print(f"파싱 에러: {e}")
        return 0

final_data = []
print(" RSU 최적 위치 탐색 자동화 시작!\n")

for loc in rsu_data:
    run_simulation(loc["id"], loc["x"], loc["y"])
    pdr = parse_pdr()
    final_data.append({"ID": loc["id"], "Lat": loc["lat"], "Lon": loc["lon"], "PDR": pdr})

df = pd.DataFrame(final_data)
df.to_csv(FINAL_CSV, index=False)

df_sorted = df.sort_values(by="PDR", ascending=False).reset_index(drop=True)

print("\n 지도 시각화 생성 중 (erlangen_rsu_map.html)...")
m = folium.Map(location=[49.5760, 11.0150], zoom_start=14, tiles='OpenStreetMap')

for idx, row in df_sorted.iterrows():
    lat, lon = row["Lat"], row["Lon"]
    pdr_val = row["PDR"]
    rsu_id = row["ID"]
    
    if idx == 0: 
        marker_color = "yellow" 
        circle_color = "yellow"
        label = f"🥇 Rank 1 (PDR: {pdr_val:.1f}%)"
    elif idx <= 3: 
        marker_color = "green"
        circle_color = "green"
        label = f"🥈 Rank {idx+1} (PDR: {pdr_val:.1f}%)"
    else: 
        marker_color = "red"
        circle_color = "red"
        label = f"Rank {idx+1} (PDR: {pdr_val:.1f}%)"

    folium.Marker(
        location=[lat, lon],
        popup=f"<b>{label}</b><br>ID: {rsu_id}",
        icon=folium.Icon(color=marker_color, icon="info-sign")
    ).add_to(m)
    
    folium.Circle(
        location=[lat, lon],
        radius=150, 
        color=circle_color,
        fill=True,
        fill_opacity=0.3 if idx <= 3 else 0.1 
    ).add_to(m)

m.save("erlangen_rsu_map.html")
print("모든 작업 완료! erlangen_rsu_map.html 파일을 브라우저에서 열어보세요.")
