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

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "ms_asa_final_results_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25  # [algo7] 좌표 보정: Y축 뒤집기+margin 추가 (기존엔 없었음)

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

NUM_STARTS = 5
T_START = 50.0
T_END = 1.0
ALPHA = 0.85
MAX_ITER = 3

MAX_STEP_SIZE = 150.0
MIN_STEP_SIZE = 5.0


def correct_coords(x, y):
    """[algo7] 검색 공간(raw offset-only) 좌표를 실제 시뮬레이션 좌표로 보정."""
    return x + MARGIN, HEIGHT - y + MARGIN


def run_simulation(sim_x, sim_y):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR)
    os.makedirs(RESULT_DIR)

    corrected_x, corrected_y = correct_coords(sim_x, sim_y)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()
    content = content.replace("RSU_X_PLACEHOLDER", f"{corrected_x:.2f}")
    content = content.replace("RSU_Y_PLACEHOLDER", f"{corrected_y:.2f}")
    with open(WORKING_INI, "w") as f:
        f.write(content)

    process = subprocess.run(
        [RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], capture_output=True, text=True
    )

    if (
        process.returncode != 0
        or "<!> Error" in process.stdout
        or "<!> Error" in process.stderr
    ):
        return -1.0

    return parse_pdr()


def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path):
        return 0.0

    try:
        total_received, rsu_generated, node_count = 0, 0, 0
        with open(result_path, "r") as f:
            content = f.read()

            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match:
                rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(
                r"node\[(\d+)\].appl\s+receivedBSMs\s+(\d+)", content
            )
            nodes_found = set()
            for node_idx, val in node_recv_matches:
                total_received += int(val)
                nodes_found.add(node_idx)
            node_count = len(nodes_found)

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles

        if expected_total == 0:
            return 0.0
        return (total_received / expected_total) * 100
    except Exception as e:
        print(f"파싱 에러: {e}")
        return 0.0


def run_single_agent_sa(agent_id, start_x, start_y):
    curr_x, curr_y = start_x, start_y
    curr_pdr = run_simulation(curr_x, curr_y)
    if curr_pdr < 0:
        curr_pdr = 0.0

    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = T_START
    history = []
    step_count = 1

    print(
        f"\n[{agent_id}] 탐색 시작! 초기 위치(X:{curr_x:.1f}, Y:{curr_y:.1f}) | PDR: {curr_pdr:.2f}%"
    )

    while temp > T_END:
        temp_ratio = (temp - T_END) / (T_START - T_END)
        current_step_limit = (
            MIN_STEP_SIZE + (MAX_STEP_SIZE - MIN_STEP_SIZE) * temp_ratio
        )

        for i in range(MAX_ITER):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, current_step_limit)
            next_x = curr_x + (math.cos(angle) * distance)
            next_y = curr_y + (math.sin(angle) * distance)

            next_x = max(0, min(WIDTH, next_x))
            next_y = max(0, min(HEIGHT, next_y))

            next_pdr = run_simulation(next_x, next_y)
            if next_pdr < 0:
                continue

            delta = next_pdr - curr_pdr
            if delta > 0:
                accept = True
            else:
                acceptance_prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < acceptance_prob

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr

            corrected_curr_x, corrected_curr_y = correct_coords(curr_x, curr_y)
            lon, lat = utm_proj(curr_x + OFFSET_X, curr_y + OFFSET_Y, inverse=True)
            history.append(
                {
                    "AgentID": agent_id,
                    "Step": step_count,
                    "Temp": temp,
                    "StepLimit": current_step_limit,
                    "Raw_X": curr_x,
                    "Raw_Y": curr_y,
                    "Sim_X": corrected_curr_x,
                    "Sim_Y": corrected_curr_y,
                    "Lat": lat,
                    "Lon": lon,
                    "PDR": curr_pdr,
                    "IsBest": (curr_pdr == best_pdr),
                }
            )
            step_count += 1

        print(
            f"  [{agent_id}] Temp: {temp:.1f} (보폭 {current_step_limit:.1f}m) -> 최고 PDR: {best_pdr:.2f}%"
        )
        temp *= ALPHA

    return best_x, best_y, best_pdr, history


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(
        f"[Multi-Start Adaptive SA, 좌표보정 적용] {NUM_STARTS}명의 탐색가 파견 시작!"
    )
    print("=" * 60)

    all_history = []
    global_best_pdr = -1.0
    global_best_x, global_best_y = 0, 0

    for i in range(1, NUM_STARTS + 1):
        start_x = random.uniform(0, WIDTH)
        start_y = random.uniform(0, HEIGHT)
        b_x, b_y, b_pdr, history = run_single_agent_sa(f"Agent_{i}", start_x, start_y)
        all_history.extend(history)
        if b_pdr > global_best_pdr:
            global_best_pdr, global_best_x, global_best_y = b_pdr, b_x, b_y

    df = pd.DataFrame(all_history)
    df.to_csv(FINAL_CSV, index=False)

    corrected_best_x, corrected_best_y = correct_coords(global_best_x, global_best_y)
    print("\n" + "=" * 60)
    print("MS-ASA 최적화 완료! (좌표보정 적용)")
    print(f"최종 명당 좌표(Sim): X={corrected_best_x:.2f}, Y={corrected_best_y:.2f}")
    print(f"달성한 최고 PDR    : {global_best_pdr:.2f}%")
    print("=" * 60)

    plt.figure(figsize=(12, 6))
    colors = ["#3498db", "#2ecc71", "#9b59b6", "#e67e22", "#1abc9c"]
    for idx, agent_id in enumerate(df["AgentID"].unique()):
        agent_data = df[df["AgentID"] == agent_id]
        plt.plot(agent_data["Step"], agent_data["PDR"], label=agent_id, alpha=0.6)
    plt.xlabel("Step")
    plt.ylabel("PDR (%)")
    plt.title("Multi-Start Adaptive SA Convergence (coordinate-corrected)")
    plt.legend()
    plt.grid(True)
    plt.savefig("ms_asa_convergence_corrected.png")
    print(
        "=> 'ms_asa_final_results_corrected.csv', 'ms_asa_convergence_corrected.png' 저장 완료!"
    )
