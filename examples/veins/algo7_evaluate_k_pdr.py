"""
algo7_evaluate_k_pdr.py
================================================================
K(RSU 설치 대수) 변화에 따른 실제 통신 성능(PDR) 평가 자동화 스크립트
================================================================

배경:
  - algo7_rsu_max_coverage.py (Greedy Max Coverage)는 순차적으로 후보를 추가하는
    알고리즘이라, final_selected_rsus_k27.csv 에 저장된 상위 K개는
    실제로 K를 직접 목표로 돌렸을 때의 결과(final_selected_rsus_k2~k5.csv)와
    동일하다. 따라서 K별로 별도 CSV 파일을 만들 필요 없이, 이 CSV 하나에서
    Rank 기준 상위 K개만 잘라서 재사용한다.
    (파일명은 "k27"이지만 실제 저장된 후보 좌표는 25개이며, K가 후보 개수를
    넘으면 자동으로 실제 개수까지만 줄여서 경고와 함께 실행한다)
  - 본 스크립트는 K=1..(후보 개수) 전체에 대해 final_selected_rsus_k27.csv의
    상위 K개 좌표를 실제로 omnetpp.ini에 배치하고, Veins/OMNeT++ 시뮬레이션
    (Cmdenv)을 직접 구동하여 "기하학적 커버리지"가 아닌 "실제 통신 성능(PDR)"을
    측정한다.
  - 무선 채널(페이딩, MAC 백오프 등)의 확률적 특성을 반영하기 위해
    같은 K에 대해 --repeats 회 반복 실행하고, 평균과 표준편차를 계산하여
    K(x축) vs PDR(y축) 에러바 차트로 시각화한다.

동작 순서 (K=1 -> 최대 후보 개수까지 반복, 각 K마다 --repeats 회 반복 실행):
  1) final_selected_rsus_k27.csv 를 한 번 로드하고, Rank 기준 상위 K개만 슬라이싱
  2) omnetpp_template.ini 를 읽어 *.numRSUs = K 로 치환하고,
     [General] 섹션 바로 아래에 K개의 rsu[i] 설정 블록 + 반복마다 달라지는
     seed-set 값을 삽입 -> omnetpp.ini 생성
  3) results/ 폴더를 매 실행 전 초기화(삭제 후 재생성)하여 이전 결과 덮어쓰기 방지
  4) ./run -u Cmdenv -c General 실행
  5) results/General-#0.sca 파싱 -> 총 발신량(BSM), 총 수신량(BSM), 차량 대수 산출
     PDR(%) = 총 수신량 / (총 발신량 * 차량 대수) * 100
  6) K별 반복 결과를 모아 평균/표준편차 계산
  7) 결과를 다음 3가지로 저장한다:
     - 반복별 원본 결과: algo7_k_vs_pdr_multirun_raw.csv
     - K별 평균/표준편차 요약(터미널 표 + CSV): algo7_k_vs_pdr_trend.csv
     - K(x축) vs PDR(y축) 에러바 차트: algo7_k_vs_pdr_errorbar.png

algo6_multi_1st2nd.py / algo7_verify_multi_rsu_pdr.py 의 좌표 배치 방식,
PDR 계산 방식(생성 BSM/수신 BSM 정규식, [General] 섹션 삽입 방식),
algo3_SA_confirm_avg.py 의 반복 실행 시 seed-set 무작위화 및 errorbarchart.py의
에러바 시각화 스타일을 그대로 계승한다.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import random
import argparse

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# 0. 경로 및 기본 설정
# ---------------------------------------------------------------------------

# 스크립트가 어느 위치에서 실행되든 항상 examples/veins 디렉터리를 기준으로 동작하도록 고정
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
RESULT_SCA = os.path.join(RESULT_DIR, "General-#0.sca")

# Greedy Max Coverage로 K=27까지 미리 뽑아둔 단일 CSV.
# Rank 기준 상위 K개를 슬라이싱해서 재사용한다 (K별 파일을 따로 만들 필요 없음).
DEFAULT_CANDIDATES_CSV = "final_selected_rsus_k27.csv"
DEFAULT_K_MIN = 1
# 파일명은 k27이지만 실제로 저장된 후보 좌표는 25개뿐이다.
# k-max를 후보 개수보다 크게 잡아도 main()에서 자동으로 실제 개수만큼 줄이고 경고를 출력한다.
DEFAULT_K_MAX = 5
DEFAULT_REPEATS = 10  # 같은 K에 대한 반복 실행 횟수 (에러바 계산용)

OUTPUT_TREND_CSV = "algo7_k_vs_pdr_trend.csv"
OUTPUT_RAW_CSV = "algo7_k_vs_pdr_multirun_raw.csv"
OUTPUT_ERRORBAR_PNG = "algo7_k_vs_pdr_errorbar.png"

# .sca 파싱용 정규식 (algo6 / algo7_verify_multi_rsu_pdr 와 동일한 패턴 계승)
RE_RSU_GENERATED = re.compile(r"rsu\[\d+\]\.appl\s+generatedBSMs\s+(\d+)")
RE_NODE_RECEIVED = re.compile(r"node\[(\d+)\]\.appl\s+receivedBSMs\s+(\d+)")

# .sca에서 차량(node) 개수를 못 찾았을 때 사용할 안전한 기본값
# (본 시나리오의 SUMO 라우트가 고정 50대 차량을 사용하는 것과 동일)
FALLBACK_NUM_VEHICLES = 50

# 결과 CSV에 실행 당시 설정을 같이 기록하기 위한 정규식.
# [algo7] 여러 조건(bitrate, 동기화 여부)을 오가며 실험하다가 나중에 결과 CSV만
# 봐서는 "이게 몇 Mbps였지?"를 알 수 없어 데이터 신뢰성 문제가 생겼던 적이 있어서 추가.
RE_BITRATE = re.compile(r"nic\.mac1609_4\.bitrate\s*=\s*([\w.]+)")
RE_AVOID_SYNC = re.compile(r"avoidBeaconSynchronization\s*=\s*(true|false)")


def get_run_config(ini_path: str = None) -> dict:
    """omnetpp_template.ini에서 이번 실행에 실제로 적용되는 핵심 설정
    (bitrate, avoidBeaconSynchronization)을 읽어온다.
    generate_ini()가 numRSUs/rsu 좌표/seed-set만 바꿔 끼우고 나머지는 템플릿을
    그대로 복사하므로, 템플릿에 적힌 값이 곧 실제 실행에 쓰이는 값이다."""
    if ini_path is None:
        ini_path = INI_TEMPLATE
    if not os.path.exists(ini_path):
        return {"Bitrate": "UNKNOWN", "AvoidBeaconSync": "UNKNOWN"}
    with open(ini_path, "r", encoding="utf-8") as f:
        content = f.read()
    bitrate_m = RE_BITRATE.search(content)
    sync_m = RE_AVOID_SYNC.search(content)
    return {
        "Bitrate": bitrate_m.group(1) if bitrate_m else "UNKNOWN",
        "AvoidBeaconSync": sync_m.group(1) if sync_m else "UNKNOWN",
    }


# ---------------------------------------------------------------------------
# 1. RSU 후보 좌표 로드 (단일 CSV에서 상위 K개 슬라이싱)
# ---------------------------------------------------------------------------

def load_all_candidates(csv_file: str) -> pd.DataFrame:
    """final_selected_rsus_k27.csv (Rank, ID, Sim_X, Sim_Y)를 한 번만 로드하고
    Rank 기준 오름차순으로 정렬해서 반환한다."""
    if not os.path.exists(csv_file):
        raise FileNotFoundError(
            f"'{csv_file}' 파일을 찾을 수 없습니다. "
            f"algo7_rsu_max_coverage.py 를 먼저 실행해서 후보 좌표 CSV를 만들었는지 확인하세요."
        )

    df = pd.read_csv(csv_file)

    required_cols = {"Rank", "Sim_X", "Sim_Y"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"'{csv_file}' 에 필요한 컬럼이 없습니다: {missing}")

    df = df.sort_values(by="Rank", ascending=True).reset_index(drop=True)
    return df


def slice_top_k(all_candidates_df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Rank 기준으로 정렬된 전체 후보 중 상위 K개만 잘라서 반환한다.
    (Greedy Max Coverage는 이미 뽑은 후보를 취소하지 않으므로, 상위 K개는
    K를 직접 목표로 돌렸을 때의 결과와 동일하다)"""
    if k > len(all_candidates_df):
        raise ValueError(
            f"K({k})가 CSV에 저장된 후보 개수({len(all_candidates_df)})보다 큽니다."
        )
    return all_candidates_df.head(k).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. ini 파일 동적 생성
# ---------------------------------------------------------------------------

def generate_ini(k: int, rsu_df: pd.DataFrame, seed: int = None) -> None:
    """omnetpp_template.ini 를 읽어 numRSUs=k 로 치환하고,
    K개 RSU 좌표 블록(+ 반복 실행용 seed-set)을 [General] 섹션 아래에 삽입하여
    omnetpp.ini 로 저장."""
    if not os.path.exists(INI_TEMPLATE):
        raise FileNotFoundError(f"'{INI_TEMPLATE}' 파일을 찾을 수 없습니다.")

    with open(INI_TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()

    # 1) *.numRSUs = K 로 강제 치환
    content = re.sub(r"\*\.numRSUs\s*=\s*\d+", f"*.numRSUs = {k}", content)

    # 2) K개 좌표로 rsu[i] 설정 블록 생성
    rsu_config_lines = [f"\n# --- [algo7] K={k} 자동 생성된 RSU 배치 ---"]
    for i, row in enumerate(rsu_df.itertuples(index=False)):
        rsu_config_lines.append(f'*.rsu[{i}].mobility.typename = "StationaryMobility"')
        rsu_config_lines.append(f"*.rsu[{i}].mobility.x = {row.Sim_X}")
        rsu_config_lines.append(f"*.rsu[{i}].mobility.y = {row.Sim_Y}")
        rsu_config_lines.append(f"*.rsu[{i}].mobility.z = 3")
        rsu_config_lines.append(f'*.rsu[{i}].applType = "TraCIDemoRSU11p"')
        rsu_config_lines.append(f"*.rsu[{i}].appl.sendBeacons = true")

    # 3) 반복 실행마다 무선 채널의 확률적 요소(페이딩/백오프 등)를 흔들기 위한 seed
    #    -> [General] 섹션 안에 있어야 -c General 실행 시 실제로 적용된다.
    if seed is not None:
        rsu_config_lines.append(f"seed-set = {seed}")

    rsu_config_lines.append("# ------------------------------------------\n")
    rsu_config = "\n".join(rsu_config_lines)

    # 4) [General] 섹션 바로 아래에 삽입 (기존 스크립트들과 동일한 방식)
    if "[General]" in content:
        content = content.replace("[General]", "[General]" + rsu_config, 1)
    else:
        content = rsu_config + content

    with open(WORKING_INI, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# 3. 시뮬레이션 실행
# ---------------------------------------------------------------------------

def append_row_to_csv(row: dict, csv_path: str) -> None:
    """[algo7] 크래시로 269/810개 결과를 통째로 날렸던 적이 있어서(로그 파싱으로
    겨우 복구), 매 반복 결과를 그 즉시 CSV에 한 줄씩 append한다. 헤더는 파일이
    없을 때만 쓴다 (mode='a'). 이러면 중간에 죽어도 그때까지의 결과는 남는다."""
    row_df = pd.DataFrame([row])
    write_header = not os.path.exists(csv_path)
    row_df.to_csv(csv_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")


def reset_results_dir() -> None:
    """이전 결과를 완전히 제거하고 빈 results 폴더를 새로 만든다."""
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)


def run_simulation(k: int, repeat: int, verbose: bool = True) -> tuple:
    """./run -u Cmdenv -c General 실행.
    반환값: (성공 여부: bool, 실측 소요시간(초): float)
    여기서 재는 시간은 시뮬레이션 안의 가상 시간(sim-time-limit=200s)이 아니라,
    실제로 이 명령어가 시작해서 끝날 때까지 걸린 현실 세계의 벽시계 시간(wall-clock time)이다.

    기존에는 subprocess.run(capture_output=True)로 출력을 전부 버퍼에 모아뒀다가
    프로세스가 끝난 뒤에야 한꺼번에 보여줬다. 그러면 omnetpp_template.ini의
    cmdenv-status-frequency=1s 설정으로 OMNeT++가 실시간으로 찍어주는 진행 상황
    (이벤트 수, 시뮬레이션 시각 등)이 화면에 안 보여서, SUMO가 실제로 잘 돌고
    있는데도 "멈춘 것처럼" 보이는 문제가 있었다.
    이제는 subprocess.Popen으로 자식 프로세스의 출력을 한 줄씩 실시간으로
    읽어서 그대로 터미널에 흘려보내면서(스트리밍), 동시에 에러 판별을 위해
    버퍼에도 모아둔다."""
    print(f"   >>> [K={k} / repeat {repeat}] 시뮬레이션 실행 중 (./run -u Cmdenv -c General) ...")
    start = time.time()

    output_lines = []
    try:
        process = subprocess.Popen(
            [RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # stderr를 stdout에 합쳐서 순서 섞이지 않게 한 스트림으로 읽음
            text=True,
            bufsize=1,  # 줄 단위 버퍼링 -> 한 줄씩 나오는 즉시 읽을 수 있게
        )
    except FileNotFoundError:
        elapsed = time.time() - start
        print(f"!! '{RUN_SCRIPT}' 실행 파일을 찾을 수 없습니다. "
              f"examples/veins 디렉터리에서 실행 중인지 확인하세요.")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"!! 시뮬레이션 실행 중 예외 발생: {e}")
        return False, elapsed

    # 자식 프로세스가 한 줄씩 출력할 때마다 즉시 화면에 흘려보낸다.
    for line in process.stdout:
        line = line.rstrip("\n")
        output_lines.append(line)
        if verbose:
            print(f"      [K={k}/r{repeat}] {line}")

    returncode = process.wait()
    elapsed = time.time() - start

    full_output = "\n".join(output_lines)
    has_error = (returncode != 0 or "<!> Error" in full_output)

    if has_error:
        print(f"!! [K={k} / repeat {repeat}] 시뮬레이션 실행 중 오류 발생 "
              f"(returncode={returncode}, 실측 소요: {elapsed:.1f}s) !!")
        tail = full_output[-1500:]
        print(tail)
        return False, elapsed

    print(f"   [K={k} / repeat {repeat}] 시뮬레이션 완료 (실측 소요시간: {elapsed:.1f}s, "
          f"시뮬레이션 내 가상시간은 200s로 고정)")
    return True, elapsed


# ---------------------------------------------------------------------------
# 4. PDR 파싱 및 계산
# ---------------------------------------------------------------------------

def parse_pdr(k: int, repeat: int, seed: int, elapsed_sec: float = 0.0) -> dict:
    """results/General-#0.sca 를 파싱하여
    총 발신량(BSM), 차량 대수, 실제 수신량, 기대 수신량, PDR(%)을 계산한다.
    elapsed_sec: 이번 반복의 실측(wall-clock) 소요시간(초). 시뮬레이션 내부
    가상시간(200s)과는 무관하며, 실제 컴퓨터가 계산에 걸린 현실 시간이다."""
    empty_result = {
        "K": k, "Repeat": repeat, "Seed": seed,
        "Total_Generated": 0, "Num_Vehicles": 0,
        "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
        "Elapsed_Sec": round(elapsed_sec, 2),
    }

    if not os.path.exists(RESULT_SCA):
        print(f"!! [K={k} / repeat {repeat}] 결과 파일이 생성되지 않았습니다: '{RESULT_SCA}' !!")
        return empty_result

    try:
        with open(RESULT_SCA, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"!! [K={k} / repeat {repeat}] 결과 파일 읽기 오류: {e} !!")
        return empty_result

    # 모든 RSU가 발신한 BSM 총합
    total_generated = sum(int(v) for v in RE_RSU_GENERATED.findall(content))

    # 모든 차량(node)이 수신한 BSM 총합 + 차량 대수(node 인덱스 종류 수)
    node_matches = RE_NODE_RECEIVED.findall(content)
    node_ids = set()
    total_received = 0
    for node_idx, val in node_matches:
        node_ids.add(node_idx)
        total_received += int(val)

    num_vehicles = len(node_ids) if node_ids else FALLBACK_NUM_VEHICLES
    if not node_ids:
        print(f"   [K={k} / repeat {repeat}] 경고: .sca에서 node[*] receivedBSMs 항목을 찾지 못해 "
              f"기본 차량 대수({FALLBACK_NUM_VEHICLES}대)를 사용합니다.")

    expected_received = total_generated * num_vehicles
    pdr = (total_received / expected_received) * 100 if expected_received > 0 else 0.0

    return {
        "K": k, "Repeat": repeat, "Seed": seed,
        "Total_Generated": total_generated,
        "Num_Vehicles": num_vehicles,
        "Expected_Received": expected_received,
        "Actual_Received": total_received,
        "PDR(%)": round(pdr, 2),
        "Elapsed_Sec": round(elapsed_sec, 2),
    }


# ---------------------------------------------------------------------------
# 5. 에러바 차트 시각화 (x축: K, y축: PDR)
# ---------------------------------------------------------------------------

def plot_errorbar_chart(summary_df: pd.DataFrame, out_path: str) -> None:
    """Plot mean PDR (y-axis) +/- standard deviation against K (x-axis) as an
    error bar chart. All labels are kept in plain ASCII/English to avoid
    font/encoding issues when rendering on Linux environments without Korean
    fonts installed (e.g. Malgun Gothic is Windows-only)."""
    plt.rcParams['axes.unicode_minus'] = False

    ks = summary_df["K"].values
    means = summary_df["PDR_Mean"].values
    stds = summary_df["PDR_Std"].values

    plt.figure(figsize=(9, 6))
    plt.errorbar(
        ks, means, yerr=stds, fmt='o-', color='royalblue',
        ecolor='lightcoral', elinewidth=2.5, capsize=8,
        markersize=9, label='Mean PDR +/- Std Dev'
    )

    for x, y in zip(ks, means):
        plt.text(x, y + (max(means) * 0.03 if len(means) else 1),
                  f"{y:.2f}%", ha='center', color='blue', fontweight='bold', fontsize=10)

    plt.xticks(ks)
    plt.xlabel("K (Number of Deployed RSUs)", fontsize=13)
    plt.ylabel("Packet Delivery Ratio (PDR) [%]", fontsize=13)
    plt.title(f"PDR vs. K (Number of RSUs) - Mean +/- Std Dev over {int(summary_df['N'].max())} runs",
              fontsize=14, pad=20)
    plt.ylim(0, max(means + stds) * 1.25 if len(means) else 100)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='best')
    plt.tight_layout()

    plt.savefig(out_path, dpi=300)
    print(f"Saved error bar chart to '{out_path}'.")
    plt.close()


# ---------------------------------------------------------------------------
# 6. 메인 실행부
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="K(RSU 대수)별 PDR 반복 평가 및 에러바 차트 생성 "
                     "(K=1..CSV에 저장된 후보 개수까지 전부, 각 K마다 여러 회 반복)"
    )
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV,
                         help=f"Rank 기준 정렬된 RSU 후보 좌표 CSV (상위 K개를 슬라이싱해서 사용) "
                              f"(기본값: {DEFAULT_CANDIDATES_CSV})")
    parser.add_argument("--k-min", type=int, default=DEFAULT_K_MIN, help="시작 K값 (기본값: 1)")
    parser.add_argument("--k-max", type=int, default=DEFAULT_K_MAX,
                         help=f"종료 K값. CSV에 저장된 후보 개수보다 크면 자동으로 줄어든다 "
                              f"(기본값: {DEFAULT_K_MAX}, 즉 CSV에 있는 만큼 전부)")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS,
                         help=f"같은 K에 대한 반복 실행 횟수 (기본값: {DEFAULT_REPEATS})")
    parser.add_argument("--seed", type=int, default=None,
                         help="재현성을 위한 random 모듈 시드 (지정하지 않으면 매 실행마다 완전 무작위)")
    parser.add_argument("--trend-out", type=str, default=OUTPUT_TREND_CSV,
                         help=f"K별 평균/표준편차 요약 CSV 파일명 (기본값: {OUTPUT_TREND_CSV})")
    parser.add_argument("--raw-out", type=str, default=OUTPUT_RAW_CSV,
                         help=f"반복별 원본 결과 CSV 파일명 (기본값: {OUTPUT_RAW_CSV})")
    parser.add_argument("--plot-out", type=str, default=OUTPUT_ERRORBAR_PNG,
                         help=f"에러바 차트 PNG 파일명 (기본값: {OUTPUT_ERRORBAR_PNG})")
    parser.add_argument("--quiet-sim", action="store_true",
                         help="./run 실행 중 OMNeT++가 찍는 실시간 상태 로그를 숨긴다 "
                              "(기본값: 출력함. 반복이 많으면 로그가 매우 길어질 수 있으므로 필요시 켜세요)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    overall_start = time.time()

    # 후보 좌표 CSV는 한 번만 로드하고, K별로 상위 K개씩 슬라이싱해서 재사용한다.
    try:
        all_candidates_df = load_all_candidates(args.candidates_csv)
    except (FileNotFoundError, ValueError) as e:
        print(f"!! {e}")
        sys.exit(1)

    print(f"'{args.candidates_csv}' 에서 후보 좌표 {len(all_candidates_df)}개 로딩 완료.")

    if args.k_max > len(all_candidates_df):
        print(f"!! 경고: k-max({args.k_max})가 후보 개수({len(all_candidates_df)})보다 큽니다. "
              f"k-max를 {len(all_candidates_df)}로 조정합니다.")
        args.k_max = len(all_candidates_df)

    run_config = get_run_config(INI_TEMPLATE)
    print("=" * 70)
    print(f" [실행 설정 확인] bitrate={run_config['Bitrate']}, "
          f"avoidBeaconSynchronization={run_config['AvoidBeaconSync']}  "
          f"('{INI_TEMPLATE}' 에서 직접 읽음, 결과 CSV에도 그대로 기록됨)")
    print("=" * 70)
    print(f" K={args.k_min}~{args.k_max} RSU 배치 대수별 PDR 반복 평가 시작 "
          f"(K당 {args.repeats}회 반복, 후보 CSV: '{args.candidates_csv}')")
    print("=" * 70)

    # [algo7] 중간에 죽어도 그때까지 결과가 남도록 매 반복마다 즉시 append하므로,
    # 이번 실행 시작 시점에 이전 raw_out 파일이 있다면 지우고 깨끗하게 새로 쓴다.
    if os.path.exists(args.raw_out):
        os.remove(args.raw_out)

    raw_results = []

    total_runs = (args.k_max - args.k_min + 1) * args.repeats
    completed_runs = 0

    def log_progress():
        """지금까지의 실측(wall-clock) 평균 소요시간을 기준으로 전체 진행률과
        예상 남은 시간(ETA)을 출력한다. (시뮬레이션 내부 가상시간 200s와는 무관)"""
        overall_elapsed = time.time() - overall_start
        avg_sec_per_run = overall_elapsed / completed_runs if completed_runs else 0.0
        remaining_runs = max(total_runs - completed_runs, 0)
        eta_sec = avg_sec_per_run * remaining_runs
        print(f"   [진행률] {completed_runs}/{total_runs}회 완료 "
              f"(누적 실측 소요: {overall_elapsed/60:.1f}분, "
              f"평균: {avg_sec_per_run:.1f}s/회, "
              f"예상 남은 시간: {eta_sec/60:.1f}분)")

    for k in range(args.k_min, args.k_max + 1):
        print(f"\n--- [K={k}] RSU {k}대 배치 실험 ({args.repeats}회 반복) ---")

        try:
            rsu_df = slice_top_k(all_candidates_df, k)
        except ValueError as e:
            print(f"!! [K={k}] {e}")
            print(f"   K={k} 는 건너뜁니다.")
            completed_runs += args.repeats  # 진행률 계산에서 건너뛴 반복도 소진된 것으로 처리
            continue

        print(f"   [K={k}] 상위 {len(rsu_df)}개 좌표 사용: "
              f"{list(zip(rsu_df['Sim_X'], rsu_df['Sim_Y']))}")

        for repeat in range(1, args.repeats + 1):
            seed = random.randint(0, 999_999)

            # 1) ini 생성 (반복마다 seed-set만 새로 부여)
            try:
                generate_ini(k, rsu_df, seed=seed)
            except FileNotFoundError as e:
                print(f"!! [K={k} / repeat {repeat}] ini 생성 실패: {e}")
                row = {
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": 0.0,
                    "Bitrate": run_config["Bitrate"], "AvoidBeaconSync": run_config["AvoidBeaconSync"],
                }
                raw_results.append(row)
                append_row_to_csv(row, args.raw_out)
                completed_runs += 1
                log_progress()
                continue

            # 2) 결과 폴더 초기화 (덮어쓰기 방지 -> 매번 깨끗하게 재생성)
            reset_results_dir()

            # 3) 시뮬레이션 실행 (실측 소요시간 측정, 실시간 로그 스트리밍)
            success, elapsed_sec = run_simulation(k, repeat, verbose=not args.quiet_sim)
            completed_runs += 1
            if not success:
                row = {
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": round(elapsed_sec, 2),
                    "Bitrate": run_config["Bitrate"], "AvoidBeaconSync": run_config["AvoidBeaconSync"],
                }
                raw_results.append(row)
                append_row_to_csv(row, args.raw_out)
                log_progress()
                continue

            # 4) PDR 파싱 및 계산
            result = parse_pdr(k, repeat, seed, elapsed_sec)
            result["Bitrate"] = run_config["Bitrate"]
            result["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
            raw_results.append(result)
            append_row_to_csv(result, args.raw_out)
            print(f"   [K={k} / repeat {repeat}] 총 발신: {result['Total_Generated']}, "
                  f"차량 대수: {result['Num_Vehicles']}, "
                  f"기대 수신: {result['Expected_Received']}, "
                  f"실제 수신: {result['Actual_Received']}, "
                  f"PDR: {result['PDR(%)']:.2f}%, "
                  f"실측 소요시간: {result['Elapsed_Sec']:.1f}s")

            # 5) 전체 진행률 및 ETA(예상 남은 시간) 출력
            log_progress()

    if not raw_results:
        print("\n!! 유효한 결과가 하나도 없습니다. CSV 파일 준비 상태를 확인하세요.")
        sys.exit(1)

    # ---------------------------------------------------------------
    # 반복별 원본 결과 저장
    # ---------------------------------------------------------------
    raw_df = pd.DataFrame(raw_results)
    # [algo7] 결과만 봐서는 어떤 bitrate/동기화 조건이었는지 알 수 없어 데이터
    # 신뢰성 문제가 생겼던 적이 있어서, 실행 시점 설정을 모든 행에 그대로 기록.
    raw_df["Bitrate"] = run_config["Bitrate"]
    raw_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")

    # ---------------------------------------------------------------
    # K별 평균/표준편차 요약 (+ K별 평균 실측 소요시간)
    # ---------------------------------------------------------------
    summary_df = raw_df.groupby("K")["PDR(%)"].agg(
        PDR_Mean="mean", PDR_Std="std", PDR_Min="min", PDR_Max="max", N="count"
    ).reset_index()
    summary_df["PDR_Std"] = summary_df["PDR_Std"].fillna(0.0)  # 반복이 1회뿐이면 std가 NaN이 되므로 0으로 처리

    elapsed_summary = raw_df.groupby("K")["Elapsed_Sec"].mean().reset_index()
    elapsed_summary = elapsed_summary.rename(columns={"Elapsed_Sec": "Elapsed_Sec_Mean"})
    summary_df = summary_df.merge(elapsed_summary, on="K", how="left")

    summary_df = summary_df.round(2)
    summary_df["Bitrate"] = run_config["Bitrate"]
    summary_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]

    display_df = summary_df.rename(columns={
        "K": "K (RSU 대수)",
        "PDR_Mean": "평균 PDR(%)",
        "PDR_Std": "표준편차(%)",
        "PDR_Min": "최소 PDR(%)",
        "PDR_Max": "최대 PDR(%)",
        "N": "반복 횟수",
        "Elapsed_Sec_Mean": "평균 실측 소요시간(s)",
    })

    print("\n" + "=" * 70)
    print(" K값에 따른 PDR 반복 평가 요약 (평균 ± 표준편차)")
    print("=" * 70)
    print(display_df.to_string(index=False))
    print("=" * 70)

    total_elapsed_sec = time.time() - overall_start
    total_sim_sec = raw_df["Elapsed_Sec"].sum()
    avg_sim_sec = total_sim_sec / len(raw_df) if len(raw_df) else 0.0
    print(f"\n[실측(wall-clock) 소요시간 요약] "
          f"스크립트 총 실행 시간: {total_elapsed_sec/60:.1f}분 "
          f"(시뮬레이션 실행 시간 합계: {total_sim_sec/60:.1f}분, "
          f"실행 횟수: {len(raw_df)}회, 1회 평균: {avg_sim_sec:.1f}s)")
    print("  참고: 이 시간은 시뮬레이션 내부 가상시간(sim-time-limit=200s)이 아니라, "
          "실제로 컴퓨터가 계산에 사용한 현실 시간입니다.")

    summary_df.to_csv(args.trend_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ K별 평균/표준편차 요약이 '{args.trend_out}' 파일로 저장되었습니다.")

    # ---------------------------------------------------------------
    # 에러바 차트 (x축: K, y축: PDR)
    # ---------------------------------------------------------------
    plot_errorbar_chart(summary_df, args.plot_out)


if __name__ == "__main__":
    main()

