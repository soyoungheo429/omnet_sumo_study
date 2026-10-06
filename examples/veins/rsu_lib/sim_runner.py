# -*- coding: utf-8 -*-
"""
rsu_lib/sim_runner.py
================================================================
"ini 만들기 -> ./run 실행 -> .sca 파싱해서 PDR 계산"을 모든 알고리즘이
공유하는 단일 구현. algo7_evaluate_k_pdr.py에서 이미 여러 번 검증된
로직을 그대로 가져옴 (num_vehicles 하드코딩 버그 등 이미 수정된 버전).
================================================================
"""

import os
import re
import shutil
import subprocess
import time

RUN_SCRIPT = "./run"
RESULT_DIR = "results"
RESULT_SCA = os.path.join(RESULT_DIR, "General-#0.sca")

RE_RSU_GENERATED = re.compile(r"rsu\[\d+\]\.appl\s+generatedBSMs\s+(\d+)")
RE_NODE_RECEIVED = re.compile(r"node\[(\d+)\]\.appl\s+receivedBSMs\s+(\d+)")

FALLBACK_NUM_VEHICLES = 50


def write_ini(
    template_path: str,
    working_ini_path: str,
    rsu_coords: list,
    k: int,
    seed: int = None,
) -> None:
    """rsu_coords: [(sim_x, sim_y), ...] 리스트. K개 RSU 블록을 [General] 아래에 삽입."""
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"\*\.numRSUs\s*=\s*\d+", f"*.numRSUs = {k}", content)

    lines = [f"\n# --- [rsu_lib] K={k} 자동 생성 ---"]
    for i, (x, y) in enumerate(rsu_coords):
        lines.append(f'*.rsu[{i}].mobility.typename = "StationaryMobility"')
        lines.append(f"*.rsu[{i}].mobility.x = {x}")
        lines.append(f"*.rsu[{i}].mobility.y = {y}")
        lines.append(f"*.rsu[{i}].mobility.z = 3")
        lines.append(f'*.rsu[{i}].applType = "TraCIDemoRSU11p"')
        lines.append(f"*.rsu[{i}].appl.sendBeacons = true")
    if seed is not None:
        lines.append(f"seed-set = {seed}")
    lines.append("# ------------------------------------\n")

    block = "\n".join(lines)
    content = (
        content.replace("[General]", "[General]" + block, 1)
        if "[General]" in content
        else block + content
    )

    with open(working_ini_path, "w", encoding="utf-8") as f:
        f.write(content)


def reset_results_dir() -> None:
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)


def run_simulation(verbose: bool = False) -> tuple:
    """반환: (성공 여부, 실측 소요시간(초), stdout 전체 텍스트)"""
    start = time.time()
    try:
        process = subprocess.Popen(
            [RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return False, time.time() - start, "run script not found"

    output_lines = []
    for line in process.stdout:
        output_lines.append(line.rstrip("\n"))
        if verbose:
            print(f"      {line.rstrip()}")

    returncode = process.wait()
    elapsed = time.time() - start
    full_output = "\n".join(output_lines)
    has_error = returncode != 0 or "<!> Error" in full_output
    return (not has_error), elapsed, full_output


def parse_pdr() -> dict:
    """.sca 파싱. 반환: {Total_Generated, Num_Vehicles, Expected_Received,
    Actual_Received, PDR}. 차량 수는 항상 .sca에서 실제로 세서 계산
    (하드코딩 금지 - 예전에 num_vehicles=50 하드코딩 버그가 있었음)."""
    empty = {
        "Total_Generated": 0,
        "Num_Vehicles": 0,
        "Expected_Received": 0,
        "Actual_Received": 0,
        "PDR": 0.0,
    }
    if not os.path.exists(RESULT_SCA):
        return empty

    with open(RESULT_SCA, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    total_generated = sum(int(v) for v in RE_RSU_GENERATED.findall(content))
    node_matches = RE_NODE_RECEIVED.findall(content)
    node_ids = set()
    total_received = 0
    for node_idx, val in node_matches:
        node_ids.add(node_idx)
        total_received += int(val)

    num_vehicles = len(node_ids) if node_ids else FALLBACK_NUM_VEHICLES
    expected = total_generated * num_vehicles
    pdr = (total_received / expected) * 100 if expected > 0 else 0.0

    return {
        "Total_Generated": total_generated,
        "Num_Vehicles": num_vehicles,
        "Expected_Received": expected,
        "Actual_Received": total_received,
        "PDR": round(pdr, 2),
    }


def parse_all(rsu_coords: list = None) -> dict:
    """[metrics] 기존 parse_pdr() 키 + 논문용 지표 전체를 한 번에 반환.
    rsu_coords는 write_ini()에 넘긴 좌표 리스트 그대로 넘기면 RSU index별 수신량이 매칭된다."""
    from rsu_lib import metrics  # 순환 import 방지용 지연 import

    base = parse_pdr()
    m = metrics.parse_metrics(RESULT_SCA, rsu_coords)
    base.update({k: v for k, v in m.items() if k not in ("PDR", "Total_Generated")})
    return base


def empty_result() -> dict:
    """시뮬레이션 실패 시 같은 컬럼 구조를 유지하기 위한 빈 결과."""
    nan = float("nan")
    return {
        "Total_Generated": 0, "Num_Vehicles": 0, "Expected_Received": 0,
        "Actual_Received": 0, "PDR": 0.0, "Num_RSUs": 0, "Total_Received": 0,
        "Service_Ratio": nan, "Jain_RSU": nan, "Jain_Vehicle": nan, "PER": nan,
        "Collisions": 0, "RXTX_Lost": 0, "RSSI_Mean_dBm": nan, "SNR_Mean_dB": nan,
        "Channel_Busy": nan, "PerRSU_Rx": "[]", "PerRSU_Source": "none", "Metrics_OK": False,
    }
