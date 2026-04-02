import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "rsu_optimization_results.csv"
SIM_TIME = 200

rsu_locations = [
    {"id": "0", "x": 1318.75, "y": 1365.05},
    {"id": "1", "x": 490.02, "y": 1517.34},
    {"id": "2", "x": 292.64, "y": 1397.32},
    {"id": "3", "x": 1879.94, "y": 1613.33},
    {"id": "4", "x": 1613.70, "y": 1704.30},
    {"id": "5", "x": 1355.88, "y": 1566.67},
    {"id": "6", "x": 935.22, "y": 1922.14},
    {"id": "7", "x": 764.28, "y": 1897.69},
    {"id": "8", "x": 742.84, "y": 1547.94},
    {"id": "9", "x": 570.19, "y": 1877.31},
    {"id": "10", "x": 219.06, "y": 933.73},
    {"id": "11", "x": 192.71, "y": 703.26},
    {"id": "12", "x": 844.81, "y": 1218.29},
    {"id": "13", "x": 933.37, "y": 1527.64},
    {"id": "14", "x": 1977.38, "y": 1232.46},
    {"id": "15", "x": 1992.64, "y": 1752.05},
    {"id": "16", "x": 1766.29, "y": 1462.92},
    {"id": "17", "x": 1392.57, "y": 1092.77},
    {"id": "18", "x": 1903.32, "y": 1893.85},
    {"id": "19", "x": 2130.14, "y": 1638.05},
    {"id": "20", "x": 1623.51, "y": 1903.04},
    {"id": "21", "x": 205.82, "y": 1547.75},
    {"id": "22", "x": 2359.88, "y": 1065.53},
    {"id": "23", "x": 540.79, "y": 1663.62},
    {"id": "24", "x": 1079.42, "y": 2001.76},
    {"id": "25", "x": 872.93, "y": 1768.10},
    {"id": "26", "x": 839.11, "y": 2088.17},
    {"id": "27", "x": 2169.45, "y": 1325.02},
    {"id": "28", "x": 385.45, "y": 1226.37},
    {"id": "29", "x": 2465.71, "y": 599.22},
    {"id": "30", "x": 1108.25, "y": 1394.45},
    {"id": "31", "x": 1087.34, "y": 1550.95},
    {"id": "32", "x": 1418.33, "y": 1995.04},
    {"id": "33", "x": 1584.98, "y": 1011.38},
    {"id": "34", "x": 2158.70, "y": 662.71},
    {"id": "35", "x": 2582.32, "y": 2018.54},
    {"id": "36", "x": 749.71, "y": 1024.75},
    {"id": "37", "x": 463.96, "y": 585.69},
    {"id": "38", "x": 2084.76, "y": 822.95},
    {"id": "39", "x": 2460.97, "y": 1244.22}
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
    
    print(f" >>> [교차로 ID: {loc_index}] 위치 ({x:.2f}, {y:.2f})에 RSU 1대 배치 후 시뮬레이션 시작...")
    
    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                            capture_output=True, text=True)
    return process.returncode

def parse_throughput(sim_time):
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    received_packets = 0
    
    try:
        with open(result_path, "r") as f:
            for line in f:
                if "receivedWSMs:count" in line:
                    received_packets = int(line.split()[-1])
                    break
        
        throughput_bps = (received_packets * 512 * 8) / sim_time
        return throughput_bps
    except Exception as e:
        print(f"로그 파싱 에러 (패킷 0개로 간주): {e}")
        return 0

final_data = []

print("🚀 RSU 최적 위치 탐색 자동화 스크립트 시작!\n")

for loc in rsu_locations:
    run_simulation(loc["id"], loc["x"], loc["y"])
    
    tp = parse_throughput(SIM_TIME)
    
    final_data.append({
        "ID": loc["id"],
        "X": loc["x"], 
        "Y": loc["y"],
        "Throughput_bps": tp
    })
    print(f"     -> 결과: {tp:.2f} bps\n")

df = pd.DataFrame(final_data)
df.to_csv(FINAL_CSV, index=False)

plt.figure(figsize=(15, 7))
df_sorted = df.sort_values(by="Throughput_bps", ascending=False)

str_ids = [str(i) for i in df_sorted["ID"]]
bars = plt.bar(str_ids, df_sorted["Throughput_bps"], color='royalblue')

plt.xlabel("RSU ID")
plt.ylabel("Throughput (bps)")
plt.title("RSU Throughput Optimization")

if len(bars) > 0:
    bars[0].set_color('red') 

plt.xticks(rotation=90)
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.tight_layout()

plt.savefig("throughput_results.png")
print("40개 시뮬레이션 모두 완료. 결과가 CSV와 그래프로 저장되었습니다.")
