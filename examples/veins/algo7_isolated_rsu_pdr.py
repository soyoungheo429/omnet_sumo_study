"""
algo7_isolated_rsu_pdr.py
================================================================
후보 RSU 27개 각각을 "단독(K=1)"으로 배치했을 때의 개별 PDR을 측정하는 스크립트
================================================================

배경:
  - algo7_evaluate_k_pdr.py는 Rank 기준 "상위 K개 누적" 방식으로 K=1..27을
    평가한다 (K=8은 Rank 1~8을 모두 함께 배치한 결과).
  - 이 스크립트는 그와 별개로, Rank 1~27 각 후보지를 "그 후보 하나만" 단독으로
    배치했을 때(K=1, 다른 RSU 없음)의 PDR을 측정한다. 이러면 각 후보지 자체의
    "단독 기여도"를 서로 겹치는 효과 없이 순수하게 비교할 수 있다
    (예: K=7->8 누적 PDR 급증이 Rank 8 후보지 자체의 특성 때문인지 확인하는 용도).
  - ini 생성/시뮬레이션 실행/.sca 파싱 로직은 algo7_evaluate_k_pdr.py의 함수를
    그대로 재사용한다 (동일 파이프라인 유지, 코드 중복 방지).

동작 순서 (Rank 1 -> 27 각각, 매 Rank마다 --repeats 회 반복):
  1) final_selected_rsus.csv 를 로드
  2) 후보 하나(해당 Rank)만 담은 1행짜리 DataFrame으로 generate_ini(k=1, ...) 호출
     -> 그 Rank 후보지 하나만 RSU로 배치된 omnetpp.ini 생성
  3) ./run -u Cmdenv -c General 실행 -> .sca 파싱 -> PDR, 실제 수신 패킷 수 기록
  4) Rank별 평균/표준편차(PDR)와 평균 수신 패킷 총량을 요약
  5) 결과를 3가지로 저장:
     - 반복별 원본 결과: algo7_isolated_rsu_multirun_raw.csv
     - Rank별 요약(터미널 표 + CSV): algo7_isolated_rsu_trend.csv
     - Rank(x축) vs PDR(y축) 에러바 차트 + Rank vs 평균 수신 패킷 수 막대 차트
"""

import os
import sys
import time
import random
import argparse

import pandas as pd
import matplotlib.pyplot as plt

# ini 생성/시뮬레이션 실행/.sca 파싱 로직은 기존 파이프라인을 그대로 재사용한다.
import algo7_evaluate_k_pdr as base

DEFAULT_CANDIDATES_CSV = "final_selected_rsus.csv"
DEFAULT_REPEATS = 10

OUTPUT_TREND_CSV = "algo7_isolated_rsu_trend.csv"
OUTPUT_RAW_CSV = "algo7_isolated_rsu_multirun_raw.csv"
OUTPUT_PDR_PLOT_PNG = "algo7_isolated_rsu_pdr_errorbar.png"
OUTPUT_RECEIVED_PLOT_PNG = "algo7_isolated_rsu_received_bar.png"


def plot_pdr_errorbar(summary_df: pd.DataFrame, out_path: str) -> None:
    """Rank(x축) vs 단독 PDR(y축) 에러바 차트."""
    plt.rcParams['axes.unicode_minus'] = False

    ranks = summary_df["Rank"].values
    means = summary_df["PDR_Mean"].values
    stds = summary_df["PDR_Std"].values

    plt.figure(figsize=(12, 6))
    plt.errorbar(
        ranks, means, yerr=stds, fmt='o-', color='seagreen',
        ecolor='lightcoral', elinewidth=2, capsize=6,
        markersize=7, label='Isolated Mean PDR +/- Std Dev'
    )
    plt.xticks(ranks)
    plt.xlabel("Candidate Rank (tested alone as K=1)", fontsize=13)
    plt.ylabel("Packet Delivery Ratio (PDR) [%]", fontsize=13)
    plt.title(f"Isolated PDR per RSU Candidate - Mean +/- Std Dev over {int(summary_df['N'].max())} runs",
              fontsize=14, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='best')
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    print(f"Saved isolated PDR error bar chart to '{out_path}'.")
    plt.close()


def plot_received_bar(summary_df: pd.DataFrame, out_path: str) -> None:
    """Rank(x축) vs 평균 실제 수신 패킷 총량(y축) 막대 차트 (수신 패킷 총량 시각화 요청 반영)."""
    plt.rcParams['axes.unicode_minus'] = False

    ranks = summary_df["Rank"].values
    received_means = summary_df["Received_Mean"].values

    plt.figure(figsize=(12, 6))
    plt.bar(ranks, received_means, color='steelblue')
    plt.xticks(ranks)
    plt.xlabel("Candidate Rank (tested alone as K=1)", fontsize=13)
    plt.ylabel("Mean Actual Received BSM Count", fontsize=13)
    plt.title("Isolated Mean Received Packet Volume per RSU Candidate", fontsize=14, pad=20)
    plt.grid(True, axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    print(f"Saved isolated received-volume bar chart to '{out_path}'.")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="후보 RSU 27개 각각을 단독(K=1)으로 배치했을 때의 개별 PDR/수신량 측정"
    )
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV,
                         help=f"Rank/Sim_X/Sim_Y가 담긴 후보 좌표 CSV (기본값: {DEFAULT_CANDIDATES_CSV})")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS,
                         help=f"같은 Rank에 대한 반복 실행 횟수 (기본값: {DEFAULT_REPEATS})")
    parser.add_argument("--seed", type=int, default=None,
                         help="재현성을 위한 random 모듈 시드 (지정하지 않으면 매 실행마다 완전 무작위)")
    parser.add_argument("--trend-out", type=str, default=OUTPUT_TREND_CSV)
    parser.add_argument("--raw-out", type=str, default=OUTPUT_RAW_CSV)
    parser.add_argument("--pdr-plot-out", type=str, default=OUTPUT_PDR_PLOT_PNG)
    parser.add_argument("--received-plot-out", type=str, default=OUTPUT_RECEIVED_PLOT_PNG)
    parser.add_argument("--quiet-sim", action="store_true",
                         help="./run 실행 중 OMNeT++ 실시간 상태 로그를 숨긴다")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    overall_start = time.time()

    try:
        all_candidates_df = base.load_all_candidates(args.candidates_csv)
    except (FileNotFoundError, ValueError) as e:
        print(f"!! {e}")
        sys.exit(1)

    n_candidates = len(all_candidates_df)
    print(f"'{args.candidates_csv}' 에서 후보 좌표 {n_candidates}개 로딩 완료.")

    run_config = base.get_run_config(base.INI_TEMPLATE)
    print("=" * 70)
    print(f" [실행 설정 확인] bitrate={run_config['Bitrate']}, "
          f"avoidBeaconSynchronization={run_config['AvoidBeaconSync']}  "
          f"('{base.INI_TEMPLATE}' 에서 직접 읽음, 결과 CSV에도 그대로 기록됨)")
    print("=" * 70)
    print(f" 후보지 {n_candidates}개 각각을 단독(K=1)으로 배치하여 PDR 평가 시작 "
          f"(후보지당 {args.repeats}회 반복)")
    print("=" * 70)

    raw_results = []
    total_runs = n_candidates * args.repeats
    completed_runs = 0

    def log_progress():
        overall_elapsed = time.time() - overall_start
        avg_sec_per_run = overall_elapsed / completed_runs if completed_runs else 0.0
        remaining_runs = max(total_runs - completed_runs, 0)
        eta_sec = avg_sec_per_run * remaining_runs
        print(f"   [진행률] {completed_runs}/{total_runs}회 완료 "
              f"(누적 실측 소요: {overall_elapsed/60:.1f}분, "
              f"평균: {avg_sec_per_run:.1f}s/회, "
              f"예상 남은 시간: {eta_sec/60:.1f}분)")

    for _, cand_row in all_candidates_df.iterrows():
        rank = int(cand_row["Rank"])
        # 이 후보지 하나만 담은 1행짜리 DataFrame -> generate_ini가 그대로 재사용 가능
        single_rsu_df = all_candidates_df[all_candidates_df["Rank"] == rank].reset_index(drop=True)

        print(f"\n--- [Rank {rank}] 단독 배치 실험 ({args.repeats}회 반복) ---")
        print(f"   좌표: (Sim_X={cand_row['Sim_X']}, Sim_Y={cand_row['Sim_Y']})")

        for repeat in range(1, args.repeats + 1):
            seed = random.randint(0, 999_999)

            base.generate_ini(1, single_rsu_df, seed=seed)
            base.reset_results_dir()

            success, elapsed_sec = base.run_simulation(rank, repeat, verbose=not args.quiet_sim)
            completed_runs += 1
            if not success:
                raw_results.append({
                    "Rank": rank, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": round(elapsed_sec, 2),
                })
                log_progress()
                continue

            result = base.parse_pdr(rank, repeat, seed, elapsed_sec)
            # base.parse_pdr의 "K" 필드를 그대로 "Rank" 의미로 사용
            result["Rank"] = result.pop("K")
            raw_results.append(result)
            print(f"   [Rank {rank} / repeat {repeat}] 총 발신: {result['Total_Generated']}, "
                  f"차량 대수: {result['Num_Vehicles']}, "
                  f"실제 수신: {result['Actual_Received']}, "
                  f"PDR: {result['PDR(%)']:.2f}%, "
                  f"실측 소요시간: {result['Elapsed_Sec']:.1f}s")
            log_progress()

    if not raw_results:
        print("\n!! 유효한 결과가 하나도 없습니다.")
        sys.exit(1)

    raw_df = pd.DataFrame(raw_results)
    raw_df["Bitrate"] = run_config["Bitrate"]
    raw_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")

    summary_df = raw_df.groupby("Rank").agg(
        PDR_Mean=("PDR(%)", "mean"),
        PDR_Std=("PDR(%)", "std"),
        PDR_Min=("PDR(%)", "min"),
        PDR_Max=("PDR(%)", "max"),
        Received_Mean=("Actual_Received", "mean"),
        Received_Std=("Actual_Received", "std"),
        N=("PDR(%)", "count"),
    ).reset_index()
    summary_df["PDR_Std"] = summary_df["PDR_Std"].fillna(0.0)
    summary_df["Received_Std"] = summary_df["Received_Std"].fillna(0.0)
    summary_df = summary_df.round(2)
    summary_df["Bitrate"] = run_config["Bitrate"]
    summary_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]

    display_df = summary_df.rename(columns={
        "Rank": "Rank (후보 순위)",
        "PDR_Mean": "평균 PDR(%)",
        "PDR_Std": "표준편차(%)",
        "PDR_Min": "최소 PDR(%)",
        "PDR_Max": "최대 PDR(%)",
        "Received_Mean": "평균 수신 패킷 수",
        "Received_Std": "수신 패킷 표준편차",
        "N": "반복 횟수",
    })

    print("\n" + "=" * 70)
    print(" 후보지별 단독(K=1) PDR / 수신 패킷 총량 요약")
    print("=" * 70)
    print(display_df.to_string(index=False))
    print("=" * 70)

    total_elapsed_sec = time.time() - overall_start
    print(f"\n[실측(wall-clock) 소요시간 요약] 총 실행 시간: {total_elapsed_sec/60:.1f}분 "
          f"(실행 횟수: {len(raw_df)}회)")

    summary_df.to_csv(args.trend_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ Rank별 요약이 '{args.trend_out}' 파일로 저장되었습니다.")

    plot_pdr_errorbar(summary_df, args.pdr_plot_out)
    plot_received_bar(summary_df, args.received_plot_out)


if __name__ == "__main__":
    main()
