"""
algo7_bitrate_sweep_k8.py
================================================================
K=8(Rank 1~8 실제 조합) 고정 상태에서 bitrate만 바꿔가며 PDR을 빠르게
미리 확인하는 스크립트 (오늘 미팅 전 예비 확인용, 정식 반복실험 아님)
================================================================

배경:
  - bitrate=27Mbps는 SINR 요구치가 높아 유효 통신거리가 짧아지고, 그 결과
    K=1~27 전체에서 PDR이 절대적으로 낮게 나왔다(0.26~1.29%).
  - bitrate를 낮추면 PDR이 얼마나 회복되는지 감을 잡기 위해, 가장 대표적인
    K=8 하나만 고정하고 802.11p 유효 bitrate 후보(6/9/12/18/24/27Mbps)를
    돌아가며 각 --repeats회(기본 5회, 빠른 확인용)씩 측정한다.
  - 원래 진행 중이던 K=1~27 정식 실험(27Mbps 기준)과는 별개의 예비 조사이며,
    끝나면 omnetpp_template.ini의 bitrate를 반드시 27Mbps로 되돌린다
    (다른 작업에 영향 주지 않도록).
"""

import argparse
import random
import re
import sys

import pandas as pd
import matplotlib.pyplot as plt

import algo7_evaluate_k_pdr as base

INI_TEMPLATE = base.INI_TEMPLATE
BITRATE_LINE_RE = re.compile(r"\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=\s*[\d.]+Mbps")

DEFAULT_CANDIDATES_CSV = "final_selected_rsus.csv"
DEFAULT_K = 8
DEFAULT_BITRATES = [6, 9, 12, 18, 24, 27]
DEFAULT_REPEATS = 5
RESTORE_BITRATE = 27  # 실험 끝나면 이 값으로 원복 (현재 합의된 설정)

OUTPUT_RAW_CSV = "algo7_bitrate_sweep_raw.csv"
OUTPUT_SUMMARY_CSV = "algo7_bitrate_sweep_summary.csv"
OUTPUT_PLOT_PNG = "algo7_bitrate_sweep_plot.png"


def set_bitrate(mbps: int) -> None:
    """omnetpp_template.ini의 bitrate 값을 지정한 Mbps로 바꿔서 다시 저장."""
    with open(INI_TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()

    if not BITRATE_LINE_RE.search(content):
        raise RuntimeError("omnetpp_template.ini에서 bitrate 설정 줄을 찾지 못했습니다.")

    new_content = BITRATE_LINE_RE.sub(f"*.**.nic.mac1609_4.bitrate = {mbps}Mbps", content)
    with open(INI_TEMPLATE, "w", encoding="utf-8") as f:
        f.write(new_content)


def main():
    parser = argparse.ArgumentParser(
        description="K 고정, bitrate만 바꿔가며 PDR 예비 확인 (미팅 전 빠른 조사용)"
    )
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--bitrates", type=str, default=",".join(str(b) for b in DEFAULT_BITRATES),
                         help="쉼표로 구분된 bitrate(Mbps) 목록")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--quiet-sim", action="store_true")
    args = parser.parse_args()

    bitrates = [int(x.strip()) for x in args.bitrates.split(",")]

    try:
        all_candidates_df = base.load_all_candidates(args.candidates_csv)
        rsu_df = base.slice_top_k(all_candidates_df, args.k)
    except (FileNotFoundError, ValueError) as e:
        print(f"!! {e}")
        sys.exit(1)

    print(f"K={args.k} 고정, bitrate {bitrates} 각 {args.repeats}회 예비 확인 시작")
    print("!! 참고: 이건 정식 반복실험이 아니라 미팅 전 빠른 사전조사입니다 (반복횟수 적음)")

    raw_rows = []
    try:
        for mbps in bitrates:
            print(f"\n--- bitrate={mbps}Mbps ---")
            set_bitrate(mbps)

            for repeat in range(1, args.repeats + 1):
                seed = random.randint(0, 999_999)
                base.generate_ini(args.k, rsu_df, seed=seed)
                base.reset_results_dir()
                success, elapsed = base.run_simulation(args.k, repeat, verbose=not args.quiet_sim)
                if not success:
                    continue
                result = base.parse_pdr(args.k, repeat, seed, elapsed)
                result["Bitrate_Mbps"] = mbps
                raw_rows.append(result)
                print(f"   [bitrate={mbps}Mbps / r{repeat}] PDR={result['PDR(%)']:.2f}%, "
                      f"수신={result['Actual_Received']}")
    finally:
        # 무슨 일이 있어도(에러 나도) 합의된 27Mbps로 반드시 되돌린다.
        set_bitrate(RESTORE_BITRATE)
        print(f"\n✔ omnetpp_template.ini의 bitrate를 {RESTORE_BITRATE}Mbps로 원복했습니다.")

    if not raw_rows:
        print("!! 유효한 결과가 없습니다.")
        sys.exit(1)

    raw_df = pd.DataFrame(raw_rows)
    raw_df.to_csv(OUTPUT_RAW_CSV, index=False, encoding="utf-8-sig")

    summary = raw_df.groupby("Bitrate_Mbps").agg(
        PDR_Mean=("PDR(%)", "mean"),
        PDR_Std=("PDR(%)", "std"),
        Received_Mean=("Actual_Received", "mean"),
        N=("PDR(%)", "count"),
    ).reset_index().round(2)
    summary["PDR_Std"] = summary["PDR_Std"].fillna(0.0)
    summary.to_csv(OUTPUT_SUMMARY_CSV, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 60)
    print(f" bitrate별 K={args.k} PDR 예비 확인 결과")
    print("=" * 60)
    print(summary.to_string(index=False))
    print("=" * 60)

    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(9, 6))
    plt.errorbar(summary["Bitrate_Mbps"], summary["PDR_Mean"], yerr=summary["PDR_Std"],
                 fmt='o-', color='seagreen', ecolor='lightcoral', capsize=6, markersize=8)
    plt.xlabel("Bitrate (Mbps)", fontsize=13)
    plt.ylabel("Mean PDR (%)", fontsize=13)
    plt.title(f"PDR vs Bitrate at K={args.k} (preview, {args.repeats} runs each)", fontsize=14, pad=16)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT_PNG, dpi=300)
    print(f"\n✔ 그래프 저장: '{OUTPUT_PLOT_PNG}'")


if __name__ == "__main__":
    main()
