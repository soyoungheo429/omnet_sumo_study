"""
algo7_estimate_dwell_speed.py
================================================================
"체류시간/정체(속도)"가 실제 PDR의 진짜 원인인지 검증하는 스크립트
================================================================

배경:
  - 순수 거리 기반 상관분석(algo7_estimate_effective_radius.py)과 건물 LOS
    반영 상관분석(algo7_estimate_effective_radius_los.py) 둘 다, 27개 후보의
    실제 단독 PDR 차이를 전혀 설명하지 못했다 (모든 상관계수 p>0.3).
  - 특히 LOS 비율이 100%(건물에 전혀 안 가려짐)인 후보끼리도 PDR이
    0.00%~1.22%로 서로 다르게 나와, 거리/건물차단 외의 제3의 요인이
    있다는 게 확인됐다.
  - omnetpp_template.ini에 스크립트로 삽입된 사고 이벤트(accidentStart=73s,
    accidentDuration=50s)와 신호등(tls)이 있어, 특정 위치는 차량이 정체/서행
    하며 오래 머물 수 있다는 가설을 세웠다. "정적 스냅샷 개수" 지표는 위치만
    셀 뿐 체류시간(=연속 성공 수신 기회)을 반영하지 못하므로, 이게 실제
    커버리지 최적화가 놓친 진짜 변수일 수 있다.

방법:
  1) vehicle_snapshots.csv(0.05s 간격)에서 같은 vehicle_id의 연속된 위치
     차이(dx, dy)와 시간 차이(dt)로 각 포인트의 순간 속도(m/s)를 역산
  2) 27개 RSU 후보 각각에 대해, 150m 이내 포인트들의 "평균 속도"와
     "정지/서행(속도 < 임계값) 포인트 비율"을 계산
  3) 평균 속도(느릴수록 정체) vs 실제 단독 PDR의 상관관계 확인 (음의 상관
     기대: 속도가 낮을수록 PDR이 높아야 가설이 맞음)
  4) 정지/서행 포인트 개수(여러 속도 임계값) vs PDR의 상관관계도 확인
  5) Rank별 요약표(평균 속도, 정지 비율, PDR)로 Rank 8이 실제로 저속/정체
     구간인지 직접 비교
"""

import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr
from scipy.spatial import cKDTree

OFFSET_X = 644465.09
OFFSET_Y = 5491786.25

DEFAULT_VEHICLE_CSV = "vehicle_snapshots.csv"
DEFAULT_CANDIDATES_CSV = "final_selected_rsus.csv"
DEFAULT_ISOLATED_TREND_CSV = "algo7_isolated_rsu_trend.csv"

MAX_RADIUS = 150.0
SPEED_THRESHOLDS = [0.5, 1.0, 2.0, 3.0, 5.0]  # m/s (정지/서행 판단 기준 후보들)

OUTPUT_RANK_SUMMARY_CSV = "algo7_dwell_speed_rank_summary.csv"
OUTPUT_CORR_CSV = "algo7_dwell_speed_correlation.csv"
OUTPUT_SCATTER_PLOT_PNG = "algo7_dwell_speed_best_scatter.png"


def compute_point_speeds(vehicle_csv: str) -> pd.DataFrame:
    """같은 vehicle_id 안에서 시간순으로 정렬 후, 연속된 두 포인트의 위치/시간
    차이로 순간 속도(m/s)를 역산한다. 각 차량의 첫 포인트는 속도를 계산할 수
    없으므로 제외한다."""
    df = pd.read_csv(vehicle_csv)
    df = df.sort_values(["vehicle_id", "time"]).reset_index(drop=True)

    df["x_local"] = df["x"] - OFFSET_X
    df["y_local"] = df["y"] - OFFSET_Y

    df["prev_x"] = df.groupby("vehicle_id")["x_local"].shift(1)
    df["prev_y"] = df.groupby("vehicle_id")["y_local"].shift(1)
    df["prev_time"] = df.groupby("vehicle_id")["time"].shift(1)

    valid = df.dropna(subset=["prev_x", "prev_y", "prev_time"]).copy()
    dt = valid["time"] - valid["prev_time"]
    dist = np.sqrt((valid["x_local"] - valid["prev_x"])**2 + (valid["y_local"] - valid["prev_y"])**2)

    # dt가 0 이하인(중복 타임스탬프) 이상치는 제외
    valid = valid[dt > 0].copy()
    dt = dt[dt > 0]
    valid["speed"] = dist.loc[valid.index] / dt

    return valid[["vehicle_id", "time", "x_local", "y_local", "speed"]].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(
        description="체류시간/정체(속도)가 27개 RSU 후보의 실제 단독 PDR 차이를 설명하는지 검증"
    )
    parser.add_argument("--vehicle-csv", type=str, default=DEFAULT_VEHICLE_CSV)
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--isolated-trend-csv", type=str, default=DEFAULT_ISOLATED_TREND_CSV)
    parser.add_argument("--rank-summary-out", type=str, default=OUTPUT_RANK_SUMMARY_CSV)
    parser.add_argument("--corr-out", type=str, default=OUTPUT_CORR_CSV)
    parser.add_argument("--scatter-plot-out", type=str, default=OUTPUT_SCATTER_PLOT_PNG)
    args = parser.parse_args()

    print(f"'{args.vehicle_csv}' 로딩 및 속도 역산 중...")
    speed_df = compute_point_speeds(args.vehicle_csv)
    print(f"✔ 속도 계산 완료: {len(speed_df)}개 포인트 "
          f"(평균 {speed_df['speed'].mean():.2f} m/s, 중앙값 {speed_df['speed'].median():.2f} m/s)")

    points = speed_df[["x_local", "y_local"]].values
    speeds = speed_df["speed"].values
    tree = cKDTree(points)

    candidates_df = pd.read_csv(args.candidates_csv)
    isolated_df = pd.read_csv(args.isolated_trend_csv)
    merged_meta = candidates_df.merge(isolated_df, on="Rank", how="inner")

    rank_rows = []
    stopped_counts = {t: [] for t in SPEED_THRESHOLDS}

    for _, row in merged_meta.iterrows():
        rank = int(row["Rank"])
        rsu_xy = (row["Sim_X"], row["Sim_Y"])

        nearby_idx = tree.query_ball_point(rsu_xy, MAX_RADIUS)
        nearby_speeds = speeds[nearby_idx]

        if len(nearby_speeds) == 0:
            avg_speed = float("nan")
        else:
            avg_speed = float(np.mean(nearby_speeds))

        rank_rows.append({
            "Rank": rank,
            "N_points_150m": len(nearby_speeds),
            "Avg_Speed_mps": round(avg_speed, 2) if len(nearby_speeds) else 0.0,
            "Median_Speed_mps": round(float(np.median(nearby_speeds)), 2) if len(nearby_speeds) else 0.0,
        })

        for t in SPEED_THRESHOLDS:
            stopped_counts[t].append(int(np.sum(nearby_speeds < t)))

    rank_summary_df = pd.DataFrame(rank_rows)
    for t in SPEED_THRESHOLDS:
        rank_summary_df[f"Stopped_count_lt_{t}mps"] = stopped_counts[t]

    rank_summary_df = rank_summary_df.merge(
        merged_meta[["Rank", "PDR_Mean", "Received_Mean"]], on="Rank", how="left"
    )
    rank_summary_df.to_csv(args.rank_summary_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" Rank별 150m 이내 평균/중앙값 속도 + 실제 단독 PDR")
    print("=" * 70)
    display_cols = ["Rank", "N_points_150m", "Avg_Speed_mps", "Median_Speed_mps",
                     "Stopped_count_lt_1.0mps", "PDR_Mean", "Received_Mean"]
    print(rank_summary_df[display_cols].to_string(index=False))
    print("=" * 70)

    # ---------------------------------------------------------------
    # 상관관계: 평균 속도(음의 상관 기대) / 정지 포인트 개수(양의 상관 기대) vs PDR
    # ---------------------------------------------------------------
    corr_rows = []

    r, p = pearsonr(rank_summary_df["Avg_Speed_mps"], rank_summary_df["PDR_Mean"])
    sr, sp = spearmanr(rank_summary_df["Avg_Speed_mps"], rank_summary_df["PDR_Mean"])
    corr_rows.append({"Metric": "Avg_Speed_mps (150m)", "Pearson_r": round(r, 4), "Pearson_p": round(p, 4),
                       "Spearman_r": round(sr, 4), "Spearman_p": round(sp, 4)})

    for t in SPEED_THRESHOLDS:
        col = f"Stopped_count_lt_{t}mps"
        r, p = pearsonr(rank_summary_df[col], rank_summary_df["PDR_Mean"])
        sr, sp = spearmanr(rank_summary_df[col], rank_summary_df["PDR_Mean"])
        corr_rows.append({"Metric": col, "Pearson_r": round(r, 4), "Pearson_p": round(p, 4),
                           "Spearman_r": round(sr, 4), "Spearman_p": round(sp, 4)})

    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(args.corr_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" 속도/정체 관련 지표 vs 실제 단독 PDR 상관계수")
    print("=" * 70)
    print(corr_df.to_string(index=False))
    print("=" * 70)

    best_row = corr_df.loc[corr_df["Pearson_r"].abs().idxmax()]
    print(f"\n✔ 절댓값 기준 상관계수가 가장 큰 지표: {best_row['Metric']} "
          f"(r={best_row['Pearson_r']}, p={best_row['Pearson_p']})")

    # ---------------------------------------------------------------
    # 산점도: 평균 속도 vs PDR (가설: 음의 상관)
    # ---------------------------------------------------------------
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(9, 7))
    plt.scatter(rank_summary_df["Avg_Speed_mps"], rank_summary_df["PDR_Mean"], color='crimson', s=60)
    for _, row in rank_summary_df.iterrows():
        plt.annotate(str(int(row["Rank"])), (row["Avg_Speed_mps"], row["PDR_Mean"]),
                     textcoords="offset points", xytext=(5, 5), fontsize=8)
    plt.xlabel("Average Vehicle Speed within 150m (m/s)", fontsize=13)
    plt.ylabel("Isolated PDR (%)", fontsize=13)
    plt.title("Average Nearby Vehicle Speed vs Actual PDR\n(labels = candidate Rank)", fontsize=13, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(args.scatter_plot_out, dpi=300)
    print(f"Saved speed-vs-PDR scatter chart to '{args.scatter_plot_out}'.")
    plt.close()


if __name__ == "__main__":
    main()
