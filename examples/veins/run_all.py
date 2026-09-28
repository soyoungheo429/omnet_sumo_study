# -*- coding: utf-8 -*-
"""
run_all.py (최상위 실행 스크립트)
================================================================
CONFIG_MATRIX에 돌리고 싶은 모든 알고리즘×파라미터 조합을 적어두면,
이 스크립트 하나가 전부 순회하며 자동으로 돌린다. 사람이(=내가) 없어도
이 파일 하나로 모든 버전을 재현 가능 (교수님 피드백 반영).

두 가지 실행 방식(type)을 지원한다:

1. type="candidate_list" (algo1, algo7처럼 "순위 매겨진 후보 CSV에서
   상위 K개를 뽑아 배치"하는 알고리즘용) — rsu_lib로 직접 시뮬레이션까지 실행.

2. type="external_script" (algo2/3/4/5처럼 격자 전수조사·반복탐색·조합
   전수조사 등 독자적인 실행 루프를 가진 알고리즘용) — 이미 검증된
   독립 스크립트(algoN_..._corrected.py)를 그대로 서브프로세스로 실행하고,
   그 결과 파일들을 experiment_results/로 자동 이동만 시켜준다.
   (각 알고리즘 내부 로직까지 rsu_lib로 통합하는 건 다음 리팩토링 단계)

주의: external_script 항목들은 하나하나가 수십 분~1시간 넘게 걸릴 수
있다. CONFIG_MATRIX에 다 넣고 python3 run_all.py 한 번으로 돌리면
"내가 없어도 알아서 순차 실행"이 되지만, 총 소요 시간이 매우 길어질 수
있으니 필요한 항목만 주석 처리해서 골라 쓸 것.
================================================================
"""

import os
import sys
import re
import shutil
import random
import subprocess
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from rsu_lib import naming, run_logger, sim_runner, config_version  # noqa: E402

BASE_INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
# 주의: "results/"는 OMNeT++가 시뮬레이션마다 통째로 지우고 새로 만드는
# 작업 폴더(results/General-#0.sca)라서 절대 이 이름을 재사용하면 안 됨.
RESULTS_BASE_DIR = "experiment_results"

# ---------------------------------------------------------------
# 여기에 돌리고 싶은 조합을 전부 적는다. 이 리스트가 "실험 계획서" 역할.
# 필요 없는 항목은 앞에 # 붙여서 꺼두면 된다 (전부 켜두면 몇 시간씩 걸릴 수 있음).
# ---------------------------------------------------------------
CONFIG_MATRIX = [
    # --- candidate_list 타입: algo1, algo7 ---
    {
        "type": "candidate_list",
        "algo": "algo1_intersection",
        "mode": "multi",
        "candidates_csv": "final_selected_rsus_algo1_corrected.csv",
        "k_values": [1, 5, 10, 15, 20, 27],
        "bitrate": "6Mbps",
        "sync": True,
        "repeats": 2,
    },
    {
        "type": "candidate_list",
        "algo": "algo7_greedy",
        "mode": "multi",
        "candidates_csv": "final_selected_rsus_corrected.csv",
        "k_values": [1, 5, 10, 15, 20, 27],
        "bitrate": "6Mbps",
        "sync": True,
        "repeats": 2,
    },
    # --- external_script 타입: algo2/3/4/5 (독자적인 실행 루프를 가진 검증된 스크립트) ---
    {
        "type": "external_script",
        "algo": "algo2_bruteforce_grid",
        "mode": "single",
        "script": "algo2_grid_150n_corrected.py",
        "output_files": [
            "bruteforce_grid_150n_corrected.csv",
            "bruteforce_heatmap_150n_corrected.png",
            "bruteforce_interactive_map_150n_corrected.html",
        ],
    },
    {
        "type": "external_script",
        "algo": "algo3_SA_standard",
        "mode": "single",
        "script": "algo3_SA_corrected.py",
        "output_files": [
            "algo3_sa_results_corrected.csv",
            "algo3_sa_convergence_corrected.png",
        ],
    },
    {
        "type": "external_script",
        "algo": "algo3_SA_smart2",
        "mode": "single",
        "script": "algo3_SA_smart2_corrected.py",
        "output_files": [
            "ms_asa_paper_params_results_corrected.csv",
            "ms_asa_paper_convergence_corrected.png",
        ],
    },
    {
        "type": "external_script",
        "algo": "algo4_GA_hybrid",
        "mode": "single",
        "script": "algo4_GA_hybrid_corrected.py",
        "output_files": [
            "ga_hybrid_final_results_corrected.csv",
            "ga_hybrid_convergence_corrected.png",
        ],
    },
    {
        "type": "external_script",
        "algo": "algo5_baseline",
        "mode": "multi",
        "script": "algo5_multi_baseline_corrected.py",
        "output_files": ["algo5_baseline_top27_c2_results_corrected.csv"],
    },
]


def set_ini_bitrate_sync(bitrate: str, sync: bool) -> None:
    """omnetpp_template.ini의 bitrate/동기화 설정을 이번 조합에 맞게 갱신."""
    with open(BASE_INI_TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r"^\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=.*$",
        f"*.**.nic.mac1609_4.bitrate = {bitrate}  # [run_all] auto-set",
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^\*\.rsu\[\*\]\.appl\.avoidBeaconSynchronization\s*=.*$",
        f"*.rsu[*].appl.avoidBeaconSynchronization = {'true' if sync else 'false'}  # [run_all] auto-set",
        content,
        flags=re.MULTILINE,
    )
    with open(BASE_INI_TEMPLATE, "w", encoding="utf-8") as f:
        f.write(content)


def run_candidate_list_combo(combo: dict) -> None:
    """algo1/algo7처럼 순위 매겨진 후보 CSV에서 K개를 뽑아 rsu_lib로 직접 실행."""
    df = pd.read_csv(combo["candidates_csv"])
    set_ini_bitrate_sync(combo["bitrate"], combo["sync"])
    config_version.snapshot_current_regime(BASE_INI_TEMPLATE)

    for k in combo["k_values"]:
        params = {
            "K": k,
            "bitrate": combo["bitrate"],
            "sync": combo["sync"],
            "candidates": os.path.basename(combo["candidates_csv"]),
        }
        name = naming.build_name(combo["algo"], combo["mode"], params)
        paths = naming.result_paths(
            RESULTS_BASE_DIR, combo["algo"], combo["mode"], name
        )

        with run_logger.RunLogger(
            paths["log_txt"].replace(".txt", ".json"),
            combo["algo"],
            combo["mode"],
            params,
        ) as log:
            rows = []
            for repeat in range(1, combo["repeats"] + 1):
                seed = random.randint(0, 999_999)
                rsu_df = df.head(k)
                coords = list(zip(rsu_df["Sim_X"], rsu_df["Sim_Y"]))

                sim_runner.write_ini(
                    BASE_INI_TEMPLATE, WORKING_INI, coords, k, seed=seed
                )
                sim_runner.reset_results_dir()
                success, elapsed, stdout_text = sim_runner.run_simulation(verbose=False)
                result = (
                    sim_runner.parse_pdr()
                    if success
                    else {
                        "Total_Generated": 0,
                        "Num_Vehicles": 0,
                        "Expected_Received": 0,
                        "Actual_Received": 0,
                        "PDR": 0.0,
                    }
                )
                result.update(
                    {
                        "K": k,
                        "Repeat": repeat,
                        "Seed": seed,
                        "Elapsed_Sec": round(elapsed, 2),
                    }
                )
                rows.append(result)
                log.log_event(**result)
                print(
                    f"[{name}] repeat {repeat}/{combo['repeats']}: PDR={result['PDR']}%"
                )

            pd.DataFrame(rows).to_csv(
                paths["raw_csv"], index=False, encoding="utf-8-sig"
            )

    print(f"완료: {combo['algo']} ({combo['mode']}) -> {RESULTS_BASE_DIR}/ 아래 저장됨")


def run_external_script_combo(combo: dict) -> None:
    """algo2/3/4/5처럼 독자적인 실행 루프를 가진 검증된 스크립트를 그대로
    서브프로세스로 실행하고, 알려진 출력 파일들을 experiment_results/로 이동."""
    name = naming.build_name(combo["algo"], combo["mode"], {})
    paths = naming.result_paths(RESULTS_BASE_DIR, combo["algo"], combo["mode"], name)

    with run_logger.RunLogger(
        paths["log_txt"].replace(".txt", ".json"),
        combo["algo"],
        combo["mode"],
        {"script": combo["script"]},
    ) as log:
        print(f"[{name}] 실행 시작: {combo['script']} (오래 걸릴 수 있음)")
        process = subprocess.run(
            ["python3", "-u", combo["script"]], capture_output=True, text=True
        )
        log.log_event(
            returncode=process.returncode,
            stdout_tail=process.stdout[-3000:],
            stderr_tail=process.stderr[-1500:],
        )

        if process.returncode != 0:
            print(
                f"[{name}] !! 실행 실패 (returncode={process.returncode}) - 로그 확인 필요"
            )
            return

        for fname in combo.get("output_files", []):
            if os.path.exists(fname):
                shutil.move(fname, os.path.join(paths["dir"], fname))
                print(f"[{name}] 결과 이동: {fname} -> {paths['dir']}/")
            else:
                print(f"[{name}] !! 예상한 출력 파일이 없음: {fname}")

    print(f"완료: {combo['algo']} ({combo['mode']}) -> {paths['dir']}/")


def run_one_combo(combo: dict) -> None:
    combo_type = combo.get("type", "candidate_list")
    if combo_type == "external_script":
        run_external_script_combo(combo)
    else:
        run_candidate_list_combo(combo)


def main():
    os.makedirs(RESULTS_BASE_DIR, exist_ok=True)
    for combo in CONFIG_MATRIX:
        run_one_combo(combo)


if __name__ == "__main__":
    main()
