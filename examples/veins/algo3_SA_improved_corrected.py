import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import shutil
import re
import math
import random
from pyproj import Proj

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = "algo3_sa_improved_results_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

N_AGENTS = 5
T_START = 10.0
T_END = 0.1
ALPHA = 0.85
MAX_ITER = 3
MAX_STEP = 150.0
MIN_STEP = 5.0


def correct_coords(x, y):
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
        print(f"파싱 에러: {e}")
        return 0.0


def step_size_for_temp(temp):
    frac = (temp - T_END) / (T_START - T_END)
    frac = max(0.0, min(1.0, frac))
    return MIN_STEP + (MAX_STEP - MIN_STEP) * frac


def run_single_agent(agent_id):
    curr_x = random.uniform(0, WIDTH)
    curr_y = random.uniform(0, HEIGHT)
    curr_pdr = run_simulation(curr_x, curr_y)

    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
    temp = T_START
    history = []
    step_count = 1

    print(f"\n[{agent_id}] 시작 (초기 PDR: {curr_pdr:.2f}%)")

    while temp > T_END:
        step_size = step_size_for_temp(temp)
        for _ in range(MAX_ITER):
            next_x = max(0, min(WIDTH, curr_x + random.uniform(-step_size, step_size)))
            next_y = max(0, min(HEIGHT, curr_y + random.uniform(-step_size, step_size)))

            print(
                f" [{agent_id} #{step_count}] Temp:{temp:.2f} Step:{step_size:.0f}m "
                f"위치(X:{next_x:.1f},Y:{next_y:.1f})... ",
                end="",
            )

            next_pdr = run_simulation(next_x, next_y)
            if next_pdr < 0:
                print("에러 발생 (스킵)")
                continue

            delta = next_pdr - curr_pdr
            if delta > 0:
                accept = True
                reason = "개선됨"
            else:
                acceptance_prob = math.exp(delta / temp) if temp > 0 else 0
                accept = random.random() < acceptance_prob
                reason = f"확률적 수락 (prob: {acceptance_prob:.3f})" if accept else "거절"

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
                    reason += " [NEW BEST!]"
                print(f"수락: {next_pdr:.2f}% ({reason})")
            else:
                print(f"거절: {next_pdr:.2f}%")

            corrected_x, corrected_y = correct_coords(curr_x, curr_y)
            lon, lat = utm_proj(curr_x + OFFSET_X, curr_y + OFFSET_Y, inverse=True)
            history.append({
                "AgentID": agent_id, "Step": step_count, "Temp": temp, "StepSize": step_size,
                "Raw_X": curr_x, "Raw_Y": curr_y,
                "Sim_X": corrected_x, "Sim_Y": corrected_y,
                "Lat": lat, "Lon": lon,
                "PDR": curr_pdr, "Accepted": accept, "IsBest": (curr_pdr == best_pdr),
            })
            step_count += 1
        temp *= ALPHA

    return best_x, best_y, best_pdr, history


if __name__ == "__main__":
    all_history = []
    global_best = None

    for i in range(1, N_AGENTS + 1):
        agent_id = f"Agent_{i}"
        bx, by, bpdr, hist = run_single_agent(agent_id)
        all_history.extend(hist)
        if global_best is None or bpdr > global_best[2]:
            global_best = (bx, by, bpdr, agent_id)

    df = pd.DataFrame(all_history)
    df.to_csv(FINAL_CSV, index=False)

    best_x, best_y, best_pdr, best_agent = global_best
    corrected_best_x, corrected_best_y = correct_coords(best_x, best_y)
    print("\n" + "=" * 50)
    print(f"Improved Multi-Start SA 완료! 1등: {best_agent}")
    print(f"최적 위치(Sim 좌표): X={corrected_best_x:.2f}, Y={corrected_best_y:.2f}")
    print(f"최고 PDR: {best_pdr:.2f}%")
    print("=" * 50)

    plt.figure(figsize=(10, 6))
    for agent_id, group in df.groupby("AgentID"):
        plt.plot(group["Step"], group["PDR"], marker="o", markersize=3, linestyle="-",
                  alpha=0.7, label=agent_id)
    best_rows = df[df["IsBest"]]
    plt.scatter(best_rows["Step"], best_rows["PDR"], color="red", s=40, zorder=5, label="Best per step")
    plt.xlabel("Step (agent별 개별 카운트)")
    plt.ylabel("PDR (%)")
    plt.title("Improved Multi-Start SA Convergence (step-size shrink 150m->5m)")
    plt.legend(fontsize=8)
    plt.grid(True)
    plt.savefig("algo3_sa_improved_convergence_corrected.png")
    print("=> 'algo3_sa_improved_results_corrected.csv', 'algo3_sa_improved_convergence_corrected.png' 저장 완료")
