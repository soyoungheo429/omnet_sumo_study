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
FINAL_CSV = "algo3_sa_results_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25  # [algo7] 좌표 보정: Y축 뒤집기+margin 추가 (기존엔 없었음)

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

T_START = 10.0
T_END = 0.1
ALPHA = 0.85
MAX_ITER = 3
STEP_SIZE = 150.0


def correct_coords(x, y):
    """[algo7] 검색 공간(raw offset-only) 좌표를 실제 시뮬레이션 좌표로 보정.
    Veins의 traci2omnet() 공식과 동일: x+margin, HEIGHT-y+margin."""
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

            node_recv_matches = re.findall(
                r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content
            )
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
        print(f"파싱 에러: {e}")
        return 0.0


def simulated_annealing():
    curr_x = random.uniform(0, WIDTH)
    curr_y = random.uniform(0, HEIGHT)
    curr_pdr = run_simulation(curr_x, curr_y)

    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr

    temp = T_START
    history = []

    step_count = 1

    print(f"\nSimulated Annealing 시작 (좌표보정 적용, 초기 PDR: {curr_pdr:.2f}%)")

    while temp > T_END:
        for i in range(MAX_ITER):
            next_x = max(0, min(WIDTH, curr_x + random.uniform(-STEP_SIZE, STEP_SIZE)))
            next_y = max(0, min(HEIGHT, curr_y + random.uniform(-STEP_SIZE, STEP_SIZE)))

            print(
                f" [{step_count}] Temp: {temp:.2f} | 시도 위치 (X: {next_x:.1f}, Y: {next_y:.1f})... ",
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
                reason = (
                    f"확률적 수락 (prob: {acceptance_prob:.3f})" if accept else "거절"
                )

            if accept:
                curr_x, curr_y, curr_pdr = next_x, next_y, next_pdr
                if curr_pdr > best_pdr:
                    best_x, best_y, best_pdr = curr_x, curr_y, curr_pdr
                    reason += " [NEW BEST!]"
                print(f"수락: {next_pdr:.2f}% ({reason})")
            else:
                print(f"거절: {next_pdr:.2f}%")

            corrected_curr_x, corrected_curr_y = correct_coords(curr_x, curr_y)
            lon, lat = utm_proj(curr_x + OFFSET_X, curr_y + OFFSET_Y, inverse=True)
            history.append(
                {
                    "Step": step_count,
                    "Temp": temp,
                    "Raw_X": curr_x,
                    "Raw_Y": curr_y,
                    "Sim_X": corrected_curr_x,
                    "Sim_Y": corrected_curr_y,
                    "Lat": lat,
                    "Lon": lon,
                    "PDR": curr_pdr,
                    "Accepted": accept,
                    "IsBest": (curr_pdr == best_pdr),
                }
            )
            step_count += 1

        temp *= ALPHA

    return best_x, best_y, best_pdr, history


if __name__ == "__main__":
    best_x, best_y, best_pdr, history = simulated_annealing()

    df = pd.DataFrame(history)
    df.to_csv(FINAL_CSV, index=False)

    corrected_best_x, corrected_best_y = correct_coords(best_x, best_y)
    print("\n" + "=" * 50)
    print("Simulated Annealing 최적화 완료! (좌표보정 적용)")
    print(f"최적 위치(Sim 좌표): X={corrected_best_x:.2f}, Y={corrected_best_y:.2f}")
    print(f"최고 PDR: {best_pdr:.2f}%")
    print("=" * 50)

    plt.figure(figsize=(10, 5))
    plt.plot(
        df["Step"], df["PDR"], marker="o", linestyle="-", color="b", label="Current PDR"
    )
    plt.plot(df[df["IsBest"]]["Step"], df[df["IsBest"]]["PDR"], "ro", label="Best PDR")
    plt.xlabel("Step")
    plt.ylabel("PDR (%)")
    plt.title("Simulated Annealing Convergence (coordinate-corrected)")
    plt.legend()
    plt.grid(True)
    plt.savefig("algo3_sa_convergence_corrected.png")
    print(
        "=> 'algo3_sa_results_corrected.csv', 'algo3_sa_convergence_corrected.png' 저장 완료"
    )
