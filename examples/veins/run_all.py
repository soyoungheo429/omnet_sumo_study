# -*- coding: utf-8 -*-
"""
run_all.py (최상위 실행 스크립트)
================================================================
CONFIG_MATRIX에 실행하고 싶은 모든 (알고리즘, 후보 CSV, 모드, K, bitrate,
동기화 여부, 반복횟수) 조합을 적어두면, 이 스크립트 하나가 전부 순회하며
돌린다. 사람이(=내가) 없어도 이 파일 하나로 모든 버전을 재현 가능.

주의: 오늘은 각 알고리즘의 "후보 선정 로직"을 algorithms/ 폴더로
아직 옮기지 않았으므로, 이미 만들어진 후보 CSV(final_selected_rsus_*.csv)를
그대로 입력으로 받는다. 후보 선정 로직까지 통합하는 건 다음 리팩토링 단계.
================================================================
"""

import os
import sys
import random
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
# ---------------------------------------------------------------
CONFIG_MATRIX = [
    {
        "algo": "algo3_SA",
        "mode": "single",
        "candidates_csv": "final_selected_rsus_corrected.csv",  # TODO: algo3 전용 corrected CSV로 교체
        "k_values": [1],
        "bitrate": "6Mbps",
        "sync": True,
        "repeats": 2,
    },
    {
        "algo": "algo4_GA",
        "mode": "single",
        "candidates_csv": "final_selected_rsus_corrected.csv",  # TODO: algo4 전용 corrected CSV로 교체
        "k_values": [1],
        "bitrate": "6Mbps",
        "sync": True,
        "repeats": 2,
    },
    {
        "algo": "algo7_greedy",
        "mode": "multi",
        "candidates_csv": "final_selected_rsus_corrected.csv",
        "k_values": [5, 8, 15],
        "bitrate": "6Mbps",
        "sync": True,
        "repeats": 2,
    },
]


def set_ini_bitrate_sync(bitrate: str, sync: bool) -> None:
    """omnetpp_template.ini의 bitrate/동기화 설정을 이번 조합에 맞게 갱신."""
    import re

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


def run_one_combo(combo: dict) -> None:
    df = pd.read_csv(combo["candidates_csv"])
    set_ini_bitrate_sync(combo["bitrate"], combo["sync"])
    # [config_version] 좌표는 안 남기고, bitrate/sync 조합("체제")만 영구 스냅샷
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


def main():
    os.makedirs(RESULTS_BASE_DIR, exist_ok=True)
    for combo in CONFIG_MATRIX:
        run_one_combo(combo)


if __name__ == "__main__":
    main()
