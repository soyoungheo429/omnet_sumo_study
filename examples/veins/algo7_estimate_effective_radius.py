"""
algo7_estimate_effective_radius.py
================================================================
27Mbps 환경에서 "실제 통신 유효거리"를 기존 데이터만으로 추정하는 스크립트 (방법 A)
================================================================

배경:
  - algo7_rsu_max_coverage.py는 radius=150m를 "이 안에 있으면 통신 성공"이라고
    가정하고 RSU 후보를 뽑았다. 그런데 bitrate=27Mbps로 올린 뒤 단독 RSU 테스트
    결과, Rank 1(150m 커버 포인트 26171개, 가장 넓음)은 PDR 1.09%인데 Rank 8
    (커버 포인트 5860개, 훨씬 적음)은 PDR 8.49%로 압도적으로 높았다.
    -> "150m 안에 몇 대 있냐"보다 "얼마나 가까이 있냐"가 실제 PDR과 더 관련
    있어 보이므로, 실제 유효거리가 150m보다 훨씬 짧을 것으로 추정된다.

방법 (거리 구간별 커버 포인트 수 vs 실제 PDR의 상관관계 분석):
  1) vehicle_snapshots.csv(전체 차량 위치, 0.05s 간격)와 final_selected_rsus.csv
     (27개 후보 좌표), algo7_isolated_rsu_trend.csv(27개 후보 단독 PDR 결과)를 로드
  2) 여러 거리 임계값 d (10m ~ 150m)에 대해, 27개 후보 각각의
     "d 이내 차량 포인트 개수"를 계산
  3) 각 d에 대해 "d 이내 포인트 개수" vs "실제 단독 PDR_Mean"의 피어슨/스피어만
     상관계수를 계산 -> 상관계수가 가장 높은 d가 "실제 유효거리"에 가장 가까움
  4) 결과를 표(CSV) + 그래프(상관계수 vs d, 그리고 최적 d에서의 산점도)로 저장

한계:
  - 후보지마다 실제 교통 패턴(속도, 체류시간, 차선 수 등)이 달라서, 순수하게
    "거리 효과"만 분리된 통제실험은 아니다 (근사적 추정). 더 정확히 하려면
    고정 거리에 프로브 수신 노드를 두는 별도 통제 실험(방법 B)이 필요하다.
"""

import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25

DEFAULT_VEHICLE_CSV = "vehicle_snapshots.csv"
DEFAULT_CANDIDATES_CSV = "final_selected_rsus.csv"
DEFAULT_ISOLATED_TREND_CSV = "algo7_isolated_rsu_trend.csv"

DEFAULT_DISTANCE_THRESHOLDS = list(range(10, 160, 10))  # 10, 20, ..., 150

OUTPUT_CORR_CSV = "algo7_effective_radius_correlation.csv"
OUTPUT_CORR_PLOT_PNG = "algo7_effective_radius_correlation.png"
OUTPUT_SCATTER_PLOT_PNG = "algo7_effective_radius_best_scatter.png"


def load_vehicle_points(vehicle_csv: str) -> np.ndarray:
    """vehicle_snapshots.csv(raw UTM 유사 좌표)를 로드하고 OMNeT++ 로컬 좌표계로 변환."""
    df = pd.read_csv(vehicle_csv)
    x = df["x"].values - OFFSET_X
    y = df["y"].values - OFFSET_Y
    return np.column_stack([x, y])


def compute_counts_within_thresholds(candidates_df: pd.DataFrame,
                                      points: np.ndarray,
                                      thresholds: list) -> pd.DataFrame:
    """27개 후보 각각에 대해, 여러 거리 임계값 이내 차량 포인트 개수를 계산."""
    from scipy.spatial import cKDTree
    tree = cKDTree(points)

    rows = []
    for _, row in candidates_df.iterrows():
        rank = int(row["Rank"])
        coord = (row["Sim_X"], row["Sim_Y"])
        counts = {"Rank": rank}
        for d in thresholds:
            idx = tree.query_ball_point(coord, d)
            counts[f"count_within_{d}m"] = len(idx)
        rows.append(counts)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="27Mbps 환경에서의 실제 통신 유효거리를 기존 데이터로 추정 (방법 A: 상관분석)"
    )
    parser.add_argument("--vehicle-csv", type=str, default=DEFAULT_VEHICLE_CSV)
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--isolated-trend-csv", type=str, default=DEFAULT_ISOLATED_TREND_CSV)
    parser.add_argument("--corr-out", type=str, default=OUTPUT_CORR_CSV)
    parser.add_argument("--corr-plot-out", type=str, default=OUTPUT_CORR_PLOT_PNG)
    parser.add_argument("--scatter-plot-out", type=str, default=OUTPUT_SCATTER_PLOT_PNG)
    args = parser.parse_args()

    print(f"'{args.vehicle_csv}' 로딩 중...")
    points = load_vehicle_points(args.vehicle_csv)
    print(f"✔ 차량 포인트 {len(points)}개 로딩 완료 (로컬 좌표 변환 완료)")

    candidates_df = pd.read_csv(args.candidates_csv)
    isolated_df = pd.read_csv(args.isolated_trend_csv)

    merged_meta = candidates_df.merge(isolated_df, on="Rank", how="inner")
    if len(merged_meta) != len(candidates_df):
        print(f"!! 경고: 후보 {len(candidates_df)}개 중 {len(merged_meta)}개만 "
              f"단독 PDR 결과와 매칭되었습니다. 두 CSV의 Rank가 일치하는지 확인하세요.")

    print(f"\n거리 임계값 {DEFAULT_DISTANCE_THRESHOLDS} 각각에 대해 "
          f"{len(merged_meta)}개 후보의 커버 포인트 수 계산 중...")
    counts_df = compute_counts_within_thresholds(merged_meta, points, DEFAULT_DISTANCE_THRESHOLDS)

    full_df = merged_meta.merge(counts_df, on="Rank", how="inner")

    # ---------------------------------------------------------------
    # 거리 임계값별 상관계수 계산 (count_within_d vs 실제 단독 PDR_Mean)
    # ---------------------------------------------------------------
    corr_rows = []
    for d in DEFAULT_DISTANCE_THRESHOLDS:
        col = f"count_within_{d}m"
        pearson_r, pearson_p = pearsonr(full_df[col], full_df["PDR_Mean"])
        spearman_r, spearman_p = spearmanr(full_df[col], full_df["PDR_Mean"])
        corr_rows.append({
            "Distance_m": d,
            "Pearson_r": round(pearson_r, 4),
            "Pearson_p": round(pearson_p, 4),
            "Spearman_r": round(spearman_r, 4),
            "Spearman_p": round(spearman_p, 4),
        })
    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(args.corr_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" 거리 임계값별 '커버 포인트 수 vs 단독 PDR' 상관계수")
    print("=" * 70)
    print(corr_df.to_string(index=False))
    print("=" * 70)

    best_row = corr_df.loc[corr_df["Pearson_r"].idxmax()]
    best_d = int(best_row["Distance_m"])
    print(f"\n✔ Pearson 상관계수가 가장 높은 거리 임계값: {best_d}m "
          f"(r={best_row['Pearson_r']}, p={best_row['Pearson_p']})")
    print(f"  -> 이 값을 '실제 유효거리' 추정치로 사용해, "
          f"algo7_rsu_max_coverage.py의 --radius를 {best_d}로 바꿔 재실행하는 것을 권장합니다.")

    print(f"\n✔ 상관계수 표가 '{args.corr_out}' 파일로 저장되었습니다.")

    # ---------------------------------------------------------------
    # 그래프 1: 거리 임계값(x) vs 상관계수(y)
    # ---------------------------------------------------------------
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(10, 6))
    plt.plot(corr_df["Distance_m"], corr_df["Pearson_r"], 'o-', color='royalblue', label='Pearson r')
    plt.plot(corr_df["Distance_m"], corr_df["Spearman_r"], 's--', color='darkorange', label='Spearman r')
    plt.axvline(best_d, color='red', linestyle=':', label=f'Best d={best_d}m')
    plt.xlabel("Distance Threshold d (m)", fontsize=13)
    plt.ylabel("Correlation with Isolated PDR", fontsize=13)
    plt.title("Correlation between 'Points within d' and Actual PDR, by Threshold d", fontsize=14, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='best')
    plt.tight_layout()
    plt.savefig(args.corr_plot_out, dpi=300)
    print(f"Saved correlation-vs-distance chart to '{args.corr_plot_out}'.")
    plt.close()

    # ---------------------------------------------------------------
    # 그래프 2: 최적 d에서의 산점도 (count_within_best_d vs PDR_Mean)
    # ---------------------------------------------------------------
    plt.figure(figsize=(9, 7))
    best_col = f"count_within_{best_d}m"
    plt.scatter(full_df[best_col], full_df["PDR_Mean"], color='seagreen', s=60)
    for _, row in full_df.iterrows():
        plt.annotate(str(int(row["Rank"])), (row[best_col], row["PDR_Mean"]),
                     textcoords="offset points", xytext=(5, 5), fontsize=8)
    plt.xlabel(f"Vehicle Points within {best_d}m of RSU Candidate", fontsize=13)
    plt.ylabel("Isolated PDR (%)", fontsize=13)
    plt.title(f"Best-fit Distance Threshold ({best_d}m): Points within d vs Actual PDR\n"
              f"(labels = candidate Rank)", fontsize=13, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(args.scatter_plot_out, dpi=300)
    print(f"Saved best-fit scatter chart to '{args.scatter_plot_out}'.")
    plt.close()


if __name__ == "__main__":
    main()
