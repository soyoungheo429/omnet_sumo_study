import os
import argparse
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
from pyproj import Proj

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)


def generate_grid_centers(width, height, step, offset_x=0.0, offset_y=0.0, bbox=None):
    x_min, x_max = (bbox[0], bbox[1]) if bbox else (0.0, width)
    y_min, y_max = (bbox[2], bbox[3]) if bbox else (0.0, height)

    candidates = []
    cand_id = 1
    rel_x = (step / 2) + offset_x
    while rel_x < width:
        if x_min <= rel_x <= x_max:
            rel_y = (step / 2) + offset_y
            while rel_y < height:
                if y_min <= rel_y <= y_max:
                    sumo_x = rel_x + OFFSET_X
                    sumo_y = rel_y + OFFSET_Y
                    sim_x = rel_x + MARGIN
                    sim_y = height - rel_y + MARGIN
                    lon, lat = utm_proj(sumo_x, sumo_y, inverse=True)
                    candidates.append({
                        "id": f"Grid_{cand_id}",
                        "rel_x": rel_x, "rel_y": rel_y,
                        "sim_x": sim_x, "sim_y": sim_y,
                        "lat": lat, "lon": lon,
                    })
                    cand_id += 1
                rel_y += step
        rel_x += step

    return candidates


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

    if process.returncode != 0:
        return False, f"Crash (Code: {process.returncode})"
    if "<!> Error" in process.stdout or "<!> Error" in process.stderr:
        return False, "Internal Error (<!> Error detected)"
    return True, ""


def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path):
        return 0.0
    try:
        with open(result_path, "r") as f:
            content = f.read()
        rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
        rsu_generated = int(rsu_gen_match.group(1)) if rsu_gen_match else 0
        node_recv_matches = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
        total_received = sum(int(v) for v in node_recv_matches)
        num_vehicles = len(node_recv_matches) if node_recv_matches else 50
        expected_total = rsu_generated * num_vehicles
        return (total_received / expected_total) * 100 if expected_total > 0 else 0.0
    except Exception as e:
        print(f"\n파싱 에러: {e}")
        return 0.0


def append_row_to_csv(row, csv_path):
    row_df = pd.DataFrame([row])
    write_header = not os.path.exists(csv_path)
    row_df.to_csv(csv_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-size", type=float, default=150.0)
    parser.add_argument("--shift", action="store_true")
    parser.add_argument("--bbox", type=str, default=None)
    parser.add_argument("--out-prefix", type=str, required=True)
    args = parser.parse_args()

    offset = args.grid_size / 2 if args.shift else 0.0
    bbox = None
    if args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split(","))
        if len(bbox) != 4:
            raise ValueError("--bbox 는 x1,x2,y1,y2 형식의 4개 값이어야 합니다.")

    final_csv = f"bruteforce_grid_{args.out_prefix}_corrected.csv"
    heatmap_png = f"bruteforce_heatmap_{args.out_prefix}_corrected.png"

    print("=" * 50)
    print(f" [재탐색 시작] grid_size={args.grid_size}m, shift={args.shift}(offset={offset}m), bbox={bbox}")
    print("=" * 50)

    candidates = generate_grid_centers(WIDTH, HEIGHT, args.grid_size, offset, offset, bbox)
    print(f"총 {len(candidates)}개의 Grid 중심 좌표가 생성되었습니다.\n")

    if os.path.exists(final_csv):
        os.remove(final_csv)

    final_data = []
    for idx, cand in enumerate(candidates):
        print(f"[{idx+1}/{len(candidates)}] {cand['id']} (X:{cand['sim_x']:.1f}, Y:{cand['sim_y']:.1f})...", end="")
        is_success, error_msg = run_simulation(cand["sim_x"], cand["sim_y"])
        pdr = parse_pdr() if is_success else -1.0
        print(f" => PDR: {pdr:.2f}%" if is_success else f" [에러] {error_msg}")

        row = {
            "ID": cand["id"], "Rel_X": cand["rel_x"], "Rel_Y": cand["rel_y"],
            "Sim_X": cand["sim_x"], "Sim_Y": cand["sim_y"],
            "Lat": cand["lat"], "Lon": cand["lon"], "PDR": pdr,
        }
        final_data.append(row)
        append_row_to_csv(row, final_csv)

    df = pd.DataFrame(final_data)
    df_valid = df[df["PDR"] >= 0]

    if not df_valid.empty:
        best_rsu = df_valid.sort_values(by="PDR", ascending=False).iloc[0]
        print("\n" + "=" * 50)
        print(f"최고 성능: {best_rsu['ID']} @ Sim({best_rsu['Sim_X']:.1f}, {best_rsu['Sim_Y']:.1f}), PDR: {best_rsu['PDR']:.2f}%")
        print("=" * 50)

        plt.figure(figsize=(10, 10))
        sc = plt.scatter(df_valid["Sim_X"], df_valid["Sim_Y"], c=df_valid["PDR"], cmap='RdYlGn_r',
                          alpha=0.8, s=60, edgecolors='k', linewidths=0.3)
        plt.colorbar(sc, label='PDR (%) - red=high')
        plt.scatter(best_rsu["Sim_X"], best_rsu["Sim_Y"], color='blue', marker='*', s=300,
                    label=f'Best: {best_rsu["PDR"]:.1f}%')
        plt.title(f"Grid Refine Search ({args.out_prefix})")
        plt.xlabel("Sim_X (corrected)")
        plt.ylabel("Sim_Y (corrected)")
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.savefig(heatmap_png, dpi=150)
        print(f"=> '{heatmap_png}' 저장 완료")
    else:
        print("\n모든 시뮬레이션에서 에러가 발생했습니다.")


if __name__ == "__main__":
    main()
