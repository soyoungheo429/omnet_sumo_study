"""
algo7_backoff_collision_correlation.py
================================================================
5단계: 특정 K값들에 대해 backoff/collision 통계를 추가로 파싱하고,
PDR과의 상관관계를 확인하는 스크립트
================================================================

배경:
  - algo7_evaluate_k_pdr.py는 generatedBSMs/receivedBSMs만 파싱해서 PDR을
    계산했고, .sca는 매 실행마다 덮어써져서 지금은 backoff/collision 통계가
    남아있지 않다.
  - .sca에는 기본으로 mac1609_4의 TimesIntoBackoff/SlotsBackoff, 그리고
    collectCollisionStatistics=true 설정 덕분에 phy80211p의 ncollisions도
    기록된다는 걸 이미 확인했다.
  - K=1~27 전체를 다시 돌리기엔 시간이 오래 걸리므로, 대표 K값 몇 개만 골라
    적은 반복횟수로 backoff/collision 통계를 추가 파싱하며 재실행한다.

동작:
  1) --k-values로 지정한 K들(예: 1,5,8,15,27) 각각에 대해 --repeats회 반복 실행
  2) PDR과 함께 아래 통계를 모든 RSU/node 모듈에서 합산해서 기록:
     - Total_TimesIntoBackoff, Total_SlotsBackoff, Total_NCollisions
  3) K별 평균 요약 + 개별 실행 단위(pooled, n=K개수*repeats) 상관분석
     (PDR vs 각 backoff/collision 지표, Pearson/Spearman)
"""

import argparse
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr

import algo7_evaluate_k_pdr as base

RESULT_SCA = base.RESULT_SCA

RE_TIMES_INTO_BACKOFF = re.compile(r"\.nic\.mac1609_4\s+TimesIntoBackoff\s+(\d+)")
RE_SLOTS_BACKOFF = re.compile(r"\.nic\.mac1609_4\s+SlotsBackoff\s+(\d+)")
RE_NCOLLISIONS = re.compile(r"\.nic\.phy80211p\s+ncollisions\s+(\d+)")

DEFAULT_CANDIDATES_CSV = "final_selected_rsus.csv"
DEFAULT_K_VALUES = "1,5,8,15,27"
DEFAULT_REPEATS = 10

OUTPUT_RAW_CSV = "algo7_backoff_collision_raw.csv"
OUTPUT_K_SUMMARY_CSV = "algo7_backoff_collision_k_summary.csv"
OUTPUT_CORR_CSV = "algo7_backoff_collision_correlation.csv"
OUTPUT_SCATTER_PNG = "algo7_backoff_collision_scatter.png"


def parse_backoff_collision():
    """.sca에서 backoff/collision 관련 통계를 모든 모듈에서 합산해서 반환."""
    if not os.path.exists(RESULT_SCA):
        return {"Total_TimesIntoBackoff": 0, "Total_SlotsBackoff": 0, "Total_NCollisions": 0}
    with open(RESULT_SCA, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return {
        "Total_TimesIntoBackoff": sum(int(v) for v in RE_TIMES_INTO_BACKOFF.findall(content)),
        "Total_SlotsBackoff": sum(int(v) for v in RE_SLOTS_BACKOFF.findall(content)),
        "Total_NCollisions": sum(int(v) for v in RE_NCOLLISIONS.findall(content)),
    }


def main():
    parser = argparse.ArgumentParser(
        description="특정 K값들에 대해 backoff/collision 통계와 PDR의 상관관계 확인"
    )
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--k-values", type=str, default=DEFAULT_K_VALUES,
                         help="쉼표로 구분된 K값 목록 (기본값: 1,5,8,15,27)")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--raw-out", type=str, default=OUTPUT_RAW_CSV)
    parser.add_argument("--k-summary-out", type=str, default=OUTPUT_K_SUMMARY_CSV)
    parser.add_argument("--corr-out", type=str, default=OUTPUT_CORR_CSV)
    parser.add_argument("--scatter-out", type=str, default=OUTPUT_SCATTER_PNG)
    parser.add_argument("--quiet-sim", action="store_true")
    args = parser.parse_args()

    k_values = [int(x.strip()) for x in args.k_values.split(",")]

    try:
        all_candidates_df = base.load_all_candidates(args.candidates_csv)
    except (FileNotFoundError, ValueError) as e:
        print(f"!! {e}")
        sys.exit(1)

    print(f"'{args.candidates_csv}' 에서 후보 좌표 {len(all_candidates_df)}개 로딩 완료.")
    print(f"대상 K값: {k_values}, 각 {args.repeats}회 반복")

    raw_rows = []
    import random
    for k in k_values:
        rsu_df = base.slice_top_k(all_candidates_df, k)
        print(f"\n--- [K={k}] backoff/collision 통계 포함 재측정 ({args.repeats}회) ---")

        for repeat in range(1, args.repeats + 1):
            seed = random.randint(0, 999_999)
            base.generate_ini(k, rsu_df, seed=seed)
            base.reset_results_dir()
            success, elapsed = base.run_simulation(k, repeat, verbose=not args.quiet_sim)
            if not success:
                continue
            pdr_result = base.parse_pdr(k, repeat, seed, elapsed)
            extra = parse_backoff_collision()
            row = {**pdr_result, **extra}
            raw_rows.append(row)
            print(f"   [K={k} / r{repeat}] PDR={row['PDR(%)']:.2f}%, "
                  f"TimesIntoBackoff={row['Total_TimesIntoBackoff']}, "
                  f"SlotsBackoff={row['Total_SlotsBackoff']}, "
                  f"NCollisions={row['Total_NCollisions']}")

    if not raw_rows:
        print("!! 유효한 결과가 없습니다.")
        sys.exit(1)

    raw_df = pd.DataFrame(raw_rows)
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")

    # K별 평균 요약
    k_summary = raw_df.groupby("K").agg(
        PDR_Mean=("PDR(%)", "mean"),
        Backoff_Mean=("Total_TimesIntoBackoff", "mean"),
        SlotsBackoff_Mean=("Total_SlotsBackoff", "mean"),
        NCollisions_Mean=("Total_NCollisions", "mean"),
        N=("PDR(%)", "count"),
    ).reset_index().round(2)
    k_summary.to_csv(args.k_summary_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" K별 평균 PDR / Backoff / Collision 요약")
    print("=" * 70)
    print(k_summary.to_string(index=False))
    print("=" * 70)

    # 개별 실행 단위(pooled, n=len(k_values)*repeats) 상관관계
    metrics = ["Total_TimesIntoBackoff", "Total_SlotsBackoff", "Total_NCollisions"]
    corr_rows = []
    for m in metrics:
        r, p = pearsonr(raw_df[m], raw_df["PDR(%)"])
        sr, sp = spearmanr(raw_df[m], raw_df["PDR(%)"])
        corr_rows.append({"Metric": m, "Pearson_r": round(r, 4), "Pearson_p": round(p, 4),
                           "Spearman_r": round(sr, 4), "Spearman_p": round(sp, 4)})
    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(args.corr_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(f" 개별 실행 단위(n={len(raw_df)}) Backoff/Collision vs PDR 상관관계")
    print("=" * 70)
    print(corr_df.to_string(index=False))
    print("=" * 70)

    # 산점도 (K별로 색 구분, x=NCollisions, y=PDR)
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(9, 7))
    for k in k_values:
        sub = raw_df[raw_df["K"] == k]
        plt.scatter(sub["Total_NCollisions"], sub["PDR(%)"], label=f"K={k}", s=50, alpha=0.8)
    plt.xlabel("Total NCollisions (per run)", fontsize=13)
    plt.ylabel("PDR (%)", fontsize=13)
    plt.title("NCollisions vs PDR by K", fontsize=14, pad=20)
    plt.legend(loc='best')
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(args.scatter_out, dpi=300)
    print(f"\nSaved scatter chart to '{args.scatter_out}'.")
    plt.close()


if __name__ == "__main__":
    main()
