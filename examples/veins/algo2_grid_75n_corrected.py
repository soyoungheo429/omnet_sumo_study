import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import folium
from pyproj import Proj

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "bruteforce_grid_75n_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
GRID_SIZE = 75.0
MARGIN = 25

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)


def generate_grid_centers(width, height, step):
    candidates = []
    num_x = int(width // step)
    num_y = int(height // step)

    cand_id = 1
    for i in range(num_x):
        for j in range(num_y):
            rel_x = (i * step) + (step / 2)
            rel_y = (j * step) + (step / 2)

            sumo_x = rel_x + OFFSET_X
            sumo_y = rel_y + OFFSET_Y

            sim_x = rel_x + MARGIN
            sim_y = HEIGHT - rel_y + MARGIN

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

    process = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"],
                              capture_output=True, text=True)

    is_success = True
    error_msg = ""

    if process.returncode != 0:
        is_success = False
        error_msg = f"Crash (Code: {process.returncode})"
    elif "<!> Error" in process.stdout or "<!> Error" in process.stderr:
        is_success = False
        error_msg = "Internal Error (<!> Error detected)"

    return is_success, error_msg, process.stdout


def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    total_received = 0
    rsu_generated = 0
    node_count = 0

    if not os.path.exists(result_path):
        return 0.0

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

        if expected_total == 0:
            return 0.0

        pdr = (total_received / expected_total) * 100
        return pdr
    except Exception as e:
        print(f"\n파싱 에러: {e}")
        return 0.0


def append_row_to_csv(row: dict, csv_path: str) -> None:
    row_df = pd.DataFrame([row])
    write_header = not os.path.exists(csv_path)
    row_df.to_csv(csv_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")


print("\n" + "=" * 50)
print(f" [전역 탐색 시작] 구역: {WIDTH}m x {HEIGHT}m, 해상도: {GRID_SIZE}m (좌표 보정 적용)")
print("=" * 50)

candidates = generate_grid_centers(WIDTH, HEIGHT, GRID_SIZE)
print(f"총 {len(candidates)}개의 Grid 중심 좌표가 생성되었습니다.\n")

if os.path.exists(FINAL_CSV):
    os.remove(FINAL_CSV)

final_data = []

for idx, cand in enumerate(candidates):
    print(f"[{idx+1}/{len(candidates)}] {cand['id']} (X:{cand['sim_x']:.1f}, Y:{cand['sim_y']:.1f})...", end="")

    is_success, error_msg, full_log = run_simulation(cand["id"], cand["sim_x"], cand["sim_y"])

    if is_success:
        pdr = parse_pdr()
        print(f" => 정상 완주! (PDR: {pdr:.2f}%)")
    else:
        pdr = -1.0
        print(f" [에러 발생] {error_msg}")

    row = {
        "ID": cand["id"],
        "Rel_X": cand["rel_x"],
        "Rel_Y": cand["rel_y"],
        "Sim_X": cand["sim_x"],
        "Sim_Y": cand["sim_y"],
        "Lat": cand["lat"],
        "Lon": cand["lon"],
        "PDR": pdr
    }
    final_data.append(row)
    append_row_to_csv(row, FINAL_CSV)

df = pd.DataFrame(final_data)

df_valid = df[df["PDR"] >= 0]

if not df_valid.empty:
    df_sorted = df_valid.sort_values(by="PDR", ascending=False).reset_index(drop=True)
    best_rsu = df_sorted.iloc[0]

    print("\n" + "=" * 50)
    print("Brute-force 탐색 완료!")
    print(f"최고 성능 RSU: {best_rsu['ID']} (Lat: {best_rsu['Lat']:.6f}, Lon: {best_rsu['Lon']:.6f})")
    print(f"달성 PDR: {best_rsu['PDR']:.2f}%")
    print("=" * 50)

    plt.figure(figsize=(10, 10))
    sc = plt.scatter(df_valid["Sim_X"], df_valid["Sim_Y"], c=df_valid["PDR"], cmap='RdYlGn_r', alpha=0.8, s=40, edgecolors='k', linewidths=0.3)
    plt.colorbar(sc, label='Packet Delivery Ratio (PDR %) - red=high')

    df_error = df[df["PDR"] == -1.0]
    if not df_error.empty:
        plt.scatter(df_error["Sim_X"], df_error["Sim_Y"], color='black', marker='x', s=30, label='Error / Crash')

    plt.scatter(best_rsu["Sim_X"], best_rsu["Sim_Y"], color='blue', marker='*', s=300, label=f'Best: {best_rsu["PDR"]:.1f}%')

    plt.title("Grid-based Global Search PDR Heatmap (coordinate-corrected)")
    plt.xlabel("Sim_X (corrected)")
    plt.ylabel("Sim_Y (corrected)")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.savefig("bruteforce_heatmap_75n_corrected.png", dpi=150)
    print("=> 'bruteforce_heatmap_75n_corrected.png' 저장 완료")

    center_lat = df_valid["Lat"].mean()
    center_lon = df_valid["Lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles='CartoDB Positron')

    for idx, row in df.iterrows():
        lat, lon, pdr_val = row["Lat"], row["Lon"], row["PDR"]

        if pdr_val == -1.0:
            color, border = "black", 1
            label = "ERROR"
        elif pdr_val == best_rsu["PDR"]:
            color, border = "blue", 3
            label = f"BEST (PDR: {pdr_val:.1f}%)"
        elif pdr_val >= 20:
            color, border = "red", 1
            label = f"PDR: {pdr_val:.1f}%"
        elif pdr_val >= 5:
            color, border = "orange", 1
            label = f"PDR: {pdr_val:.1f}%"
        else:
            color, border = "green", 0
            label = f"PDR: {pdr_val:.1f}%"

        folium.CircleMarker(
            location=[lat, lon],
            radius=4 + border,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=f"<b>{label}</b><br>ID: {row['ID']}"
        ).add_to(m)

    m.save("bruteforce_interactive_map_75n_corrected.html")
    print("=> 'bruteforce_interactive_map_75n_corrected.html' 저장 완료\n")

else:
    print("\n모든 시뮬레이션에서 에러가 발생했습니다. 로그를 확인해주세요.")
