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
FINAL_CSV = "algo4_ga_results_corrected.csv"

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25
WIDTH = 2606.46
HEIGHT = 3009.73
MARGIN = 25  # [algo7] 좌표 보정: Y축 뒤집기+margin 추가 (기존엔 없었음)

proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
utm_proj = Proj(proj_str)

POP_SIZE = 9
GEN_MAX = 5
MUTATION_RATE = 0.2
CROSSOVER_RATE = 0.8


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
        total_received = 0
        rsu_generated = 0
        with open(result_path, "r") as f:
            content = f.read()
            rsu_gen_match = re.search(r"rsu\[0\].appl\s+generatedBSMs\s+(\d+)", content)
            if rsu_gen_match:
                rsu_generated = int(rsu_gen_match.group(1))

            node_recv_matches = re.findall(
                r"node\[(\d+)\].appl\s+receivedBSMs\s+(\d+)", content
            )
            nodes = set()
            for node_idx, val in node_recv_matches:
                total_received += int(val)
                nodes.add(node_idx)
            node_count = len(nodes)

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles
        if expected_total == 0:
            return 0.0
        return (total_received / expected_total) * 100
    except Exception:
        return 0.0


def generate_initial_population():
    # 에를랑겐 맵의 특정 Edge (id: 4319352#1) 형상 데이터 기반 9개 점
    edge_shape = [
        (644909.66, 5493593.74),
        (644918.42, 5493589.42),
        (644967.49, 5493565.92),
        (644996.86, 5493554.99),
        (645048.18, 5493536.80),
        (645085.26, 5493525.56),
        (645130.08, 5493513.21),
        (645188.80, 5493499.81),
        (645239.38, 5493491.34),
        (645277.77, 5493487.84),
        (645289.29, 5493486.63),
        (645307.62, 5493484.97),
        (645348.32, 5493482.58),
        (645398.23, 5493478.81),
        (645555.88, 5493464.89),
    ]

    selected_indices = [
        int(i * (len(edge_shape) - 1) / (POP_SIZE - 1)) for i in range(POP_SIZE)
    ]

    population = []
    for idx in selected_indices:
        abs_x, abs_y = edge_shape[idx]
        # [algo7] raw offset-only 좌표 (탐색 공간). 실제 ini 기록 시점에 correct_coords() 적용
        x = abs_x - OFFSET_X
        y = abs_y - OFFSET_Y
        population.append({"x": x, "y": y, "pdr": -1.0})

    print("초기 부모 9개 점 선정 완료 (Edge id: 4319352#1 기반, 좌표보정 적용)")
    return population


def weighted_crossover(p1, p2):
    total_pdr = p1["pdr"] + p2["pdr"]
    if total_pdr <= 0:
        w1, w2 = 0.5, 0.5
    else:
        w1 = p1["pdr"] / total_pdr
        w2 = p2["pdr"] / total_pdr

    child_x = p1["x"] * w1 + p2["x"] * w2
    child_y = p1["y"] * w1 + p2["y"] * w2

    if random.random() < 0.3:
        ext_factor = random.uniform(1.1, 1.3)
        child_x = p2["x"] + (p1["x"] - p2["x"]) * ext_factor
        child_y = p2["y"] + (p1["y"] - p2["y"]) * ext_factor

    return {"x": child_x, "y": child_y, "pdr": -1.0}


def mutate(ind):
    if random.random() < MUTATION_RATE:
        move_dist = random.uniform(50, 200)
        angle = random.uniform(0, 2 * math.pi)
        ind["x"] = max(0, min(WIDTH, ind["x"] + move_dist * math.cos(angle)))
        ind["y"] = max(0, min(HEIGHT, ind["y"] + move_dist * math.sin(angle)))
    return ind


def run_ga():
    print("Genetic Algorithm 시작 (좌표보정 적용)...")
    population = generate_initial_population()
    history = []

    best_ind = None

    for gen in range(GEN_MAX):
        print(f"\n--- 세대 {gen + 1} ---")

        for i, ind in enumerate(population):
            if ind["pdr"] < 0:
                print(
                    f"  [Ind {i + 1}/{POP_SIZE}] 위치 ({ind['x']:.1f}, {ind['y']:.1f}) 평가 중...",
                    end="",
                )
                ind["pdr"] = run_simulation(ind["x"], ind["y"])
                print(f" PDR: {ind['pdr']:.2f}%")

            if best_ind is None or ind["pdr"] > best_ind["pdr"]:
                best_ind = ind.copy()

            corrected_x, corrected_y = correct_coords(ind["x"], ind["y"])
            lon, lat = utm_proj(ind["x"] + OFFSET_X, ind["y"] + OFFSET_Y, inverse=True)
            history.append(
                {
                    "Generation": gen,
                    "Raw_X": ind["x"],
                    "Raw_Y": ind["y"],
                    "Sim_X": corrected_x,
                    "Sim_Y": corrected_y,
                    "Lat": lat,
                    "Lon": lon,
                    "PDR": ind["pdr"],
                }
            )

        new_population = [best_ind.copy()]

        while len(new_population) < POP_SIZE:
            parents = random.choices(
                population, weights=[max(0.1, p["pdr"]) for p in population], k=2
            )

            if random.random() < CROSSOVER_RATE:
                child = weighted_crossover(parents[0], parents[1])
            else:
                child = random.choice(parents).copy()
                child["pdr"] = -1.0

            child = mutate(child)
            new_population.append(child)

        population = new_population

    return best_ind, history


if __name__ == "__main__":
    random.seed(42)
    best_rsu, history = run_ga()

    df = pd.DataFrame(history)
    df.to_csv(FINAL_CSV, index=False)

    corrected_best_x, corrected_best_y = correct_coords(best_rsu["x"], best_rsu["y"])
    print("\n" + "=" * 50)
    print("GA 최적화 완료! (좌표보정 적용)")
    print(f"최적 위치(Sim 좌표): X={corrected_best_x:.2f}, Y={corrected_best_y:.2f}")
    print(f"최고 PDR: {best_rsu['pdr']:.2f}%")
    print("=" * 50)

    plt.figure(figsize=(10, 5))
    plt.xlabel("Generation")
    plt.ylabel("PDR (%)")
    plt.title("GA Convergence (coordinate-corrected)")
    plt.grid(True)
    plt.savefig("algo4_ga_convergence_corrected.png")
    print(
        "=> 'algo4_ga_results_corrected.csv', 'algo4_ga_convergence_corrected.png' 저장 완료"
    )
