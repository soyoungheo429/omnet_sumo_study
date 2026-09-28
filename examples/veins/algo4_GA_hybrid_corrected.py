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
FINAL_CSV = "ga_hybrid_final_results_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25  # [algo7] 좌표 보정: Y축 뒤집기+margin 추가 (기존엔 없었음)

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

POP_SIZE = 10
MAX_GENERATIONS = 10
ELITISM_COUNT = 1

MAX_SIGMA = 150.0
MIN_SIGMA = 5.0


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


def tournament_selection(population):
    """토너먼트 선택: 무작위 3명 중 1등(부모) 선발"""
    competitors = random.sample(population, 3)
    competitors.sort(key=lambda ind: ind["pdr"], reverse=True)
    return competitors[0]


def crossover_and_mutate(parent1, parent2, current_gen):
    """가중 평균 교차 + 적응형 가우시안 돌연변이 결합"""
    total_pdr = parent1["pdr"] + parent2["pdr"]
    if total_pdr <= 0:
        w1, w2 = 0.5, 0.5
    else:
        w1 = parent1["pdr"] / total_pdr
        w2 = parent2["pdr"] / total_pdr

    m_x = (parent1["x"] * w1) + (parent2["x"] * w2)
    m_y = (parent1["y"] * w1) + (parent2["y"] * w2)

    ratio = current_gen / MAX_GENERATIONS
    current_sigma = MAX_SIGMA - (MAX_SIGMA - MIN_SIGMA) * ratio

    child_x = random.gauss(m_x, current_sigma)
    child_y = random.gauss(m_y, current_sigma)

    child_x = max(0, min(WIDTH, child_x))
    child_y = max(0, min(HEIGHT, child_y))

    return child_x, child_y


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("[Hybrid GA, 좌표보정 적용] 연속 공간 유전 알고리즘 최적화 시작!")
    print(f"인구 수: {POP_SIZE}, 최대 세대: {MAX_GENERATIONS}")
    print("=" * 60)

    population = [
        {"x": random.uniform(0, WIDTH), "y": random.uniform(0, HEIGHT), "pdr": 0.0}
        for _ in range(POP_SIZE)
    ]

    history = []
    global_best_pdr = -1.0
    global_best_x, global_best_y = 0.0, 0.0

    for gen in range(1, MAX_GENERATIONS + 1):
        print(f"\n[Generation {gen}/{MAX_GENERATIONS}] 적합도 평가 중...")

        for i, ind in enumerate(population):
            if ind["pdr"] <= 0.0:
                ind["pdr"] = run_simulation(ind["x"], ind["y"])
                if ind["pdr"] < 0:
                    ind["pdr"] = 0.0

            if ind["pdr"] > global_best_pdr:
                global_best_pdr, global_best_x, global_best_y = (
                    ind["pdr"],
                    ind["x"],
                    ind["y"],
                )

            corrected_x, corrected_y = correct_coords(ind["x"], ind["y"])
            lon, lat = utm_proj(ind["x"] + OFFSET_X, ind["y"] + OFFSET_Y, inverse=True)
            history.append(
                {
                    "Gen": gen,
                    "Ind_ID": i + 1,
                    "Raw_X": ind["x"],
                    "Raw_Y": ind["y"],
                    "Sim_X": corrected_x,
                    "Sim_Y": corrected_y,
                    "Lat": lat,
                    "Lon": lon,
                    "PDR": ind["pdr"],
                    "IsBest": (ind["pdr"] == global_best_pdr),
                }
            )

        population.sort(key=lambda item: item["pdr"], reverse=True)
        print(
            f"세대 1등: {population[0]['pdr']:.2f}% | 세대 평균: {sum(ind['pdr'] for ind in population) / POP_SIZE:.2f}%"
        )

        if gen == MAX_GENERATIONS:
            break

        next_population = []
        for i in range(ELITISM_COUNT):
            next_population.append(population[i].copy())

        while len(next_population) < POP_SIZE:
            p1 = tournament_selection(population)
            p2 = tournament_selection(population)
            c_x, c_y = crossover_and_mutate(p1, p2, gen)
            next_population.append({"x": c_x, "y": c_y, "pdr": 0.0})

        population = next_population

    df = pd.DataFrame(history)
    df.to_csv(FINAL_CSV, index=False)

    corrected_best_x, corrected_best_y = correct_coords(global_best_x, global_best_y)
    print("\n" + "=" * 60)
    print(
        f"GA 진화 완료! (좌표보정 적용) 최종 명당(Sim): X={corrected_best_x:.2f}, Y={corrected_best_y:.2f} (PDR: {global_best_pdr:.2f}%)"
    )
    print("=" * 60)

    plt.figure(figsize=(10, 5))
    gen_stats = df.groupby("Gen")["PDR"].agg(["max", "mean"]).reset_index()
    plt.plot(
        gen_stats["Gen"],
        gen_stats["max"],
        marker="*",
        color="r",
        label="Max PDR per Gen",
    )
    plt.plot(
        gen_stats["Gen"],
        gen_stats["mean"],
        marker="o",
        color="b",
        linestyle="--",
        label="Average PDR per Gen",
    )
    plt.xlabel("Generation")
    plt.ylabel("PDR (%)")
    plt.title("Hybrid GA Convergence (coordinate-corrected)")
    plt.legend()
    plt.grid(True)
    plt.savefig("ga_hybrid_convergence_corrected.png")
    print(
        "=> 'ga_hybrid_final_results_corrected.csv', 'ga_hybrid_convergence_corrected.png' 저장 완료!"
    )
