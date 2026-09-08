"""
algo7_estimate_effective_radius_los.py
================================================================
건물 장애물(Line-of-Sight 차단)을 반영한 "실제 유효 커버리지" 추정 스크립트 (방법 A 확장판)
================================================================

배경:
  - algo7_estimate_effective_radius.py(순수 거리 기반 상관분석)는 모든 거리
    임계값에서 상관계수가 사실상 0(p>0.3)으로 나와, "단순 거리"로는 27개
    후보지의 실제 단독 PDR 차이를 설명하지 못했다.
  - config.xml의 SimpleObstacleShadowing(db-per-cut=9, db-per-meter=0.4)을
    보면, 건물에 신호가 막히는지(Line-of-Sight 여부)가 실제 감쇠에 큰 영향을
    준다. 즉 "가까운데도 안 되는 곳"은 건물에 가려진 곳이고, "먼데도 잘 되는
    곳"은 시야가 트인 곳일 수 있다는 가설을 검증한다.

방법:
  1) erlangen.poly.xml에서 건물 폴리곤(type="building")을 로드 (UTM 유사
     좌표 -> OMNeT++ 로컬 좌표로 변환)
  2) 27개 RSU 후보 각각에 대해, 150m 이내 차량 포인트 중 "RSU-차량 직선이
     어떤 건물 폴리곤의 변과도 교차하지 않는" 점만 "LOS(시야 확보)"로 표시
     (건물 탐색은 KDTree로 후보 건물만 빠르게 필터링 후 정밀 교차 판정)
  3) 여러 거리 임계값 d에 대해 "d 이내 & LOS인 포인트 개수"를 계산하고,
     실제 단독 PDR과의 피어슨/스피어만 상관계수를 계산 (순수 거리 버전과 비교)
  4) Rank별 "150m 이내 전체/LOS/차단" 개수 요약표도 같이 출력해서, 특정
     Rank(예: Rank 8 vs Rank 6)가 실제로 시야가 트여있는지 직접 확인 가능하게 함
"""

import argparse
import re
import time

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
DEFAULT_POLY_XML = "erlangen.poly.xml"

MAX_RADIUS = 150.0  # 이 이상은 원래도 커버리지 후보가 아니었으므로 애초에 제외
DISTANCE_THRESHOLDS = list(range(10, 160, 10))

OUTPUT_LOS_CORR_CSV = "algo7_effective_radius_los_correlation.csv"
OUTPUT_RANK_SUMMARY_CSV = "algo7_los_rank_summary.csv"
OUTPUT_CORR_PLOT_PNG = "algo7_effective_radius_los_correlation.png"
OUTPUT_SCATTER_PLOT_PNG = "algo7_effective_radius_los_best_scatter.png"

POLY_RE = re.compile(r'<poly\b[^>]*\btype="building"[^>]*\bshape="([^"]+)"')


def load_buildings(poly_xml: str):
    """erlangen.poly.xml에서 건물 폴리곤을 로드하고 로컬 좌표로 변환.
    반환: buildings = list of Nx2 ndarray(각 폴리곤의 꼭짓점, 첫점=끝점으로 닫혀있음)"""
    with open(poly_xml, "r", encoding="iso-8859-1") as f:
        content = f.read()

    buildings = []
    for shape_str in POLY_RE.findall(content):
        pts = []
        for pair in shape_str.strip().split():
            x_str, y_str = pair.split(",")
            pts.append((float(x_str) - OFFSET_X, float(y_str) - OFFSET_Y))
        if len(pts) >= 3:
            buildings.append(np.array(pts))
    return buildings


def build_building_index(buildings):
    """건물마다 중심점(centroid)과 바운딩 반경(centroid에서 가장 먼 꼭짓점까지 거리)을
    계산해 KDTree를 구성한다. 세그먼트 근처 건물만 빠르게 걸러내는 용도."""
    centroids = np.array([b.mean(axis=0) for b in buildings])
    radii = np.array([
        np.max(np.linalg.norm(b - c, axis=1))
        for b, c in zip(buildings, centroids)
    ])
    tree = cKDTree(centroids)
    max_radius = radii.max() if len(radii) else 0.0
    return tree, radii, max_radius


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(p1, p2, p3, p4):
    """선분 p1-p2 와 p3-p4 가 교차하는지 (표준 CCW 방향성 판정)."""
    return (_ccw(p1, p3, p4) != _ccw(p2, p3, p4)) and (_ccw(p1, p2, p3) != _ccw(p1, p2, p4))


def has_line_of_sight(rsu_xy, point_xy, buildings, tree, radii, max_building_radius):
    """rsu_xy - point_xy 직선이 어떤 건물 폴리곤의 변과도 교차하지 않으면 True(시야 확보)."""
    mid = ((rsu_xy[0] + point_xy[0]) / 2.0, (rsu_xy[1] + point_xy[1]) / 2.0)
    half_len = np.linalg.norm(np.array(rsu_xy) - np.array(point_xy)) / 2.0
    search_r = half_len + max_building_radius

    nearby_idx = tree.query_ball_point(mid, search_r)
    for idx in nearby_idx:
        poly = buildings[idx]
        n = len(poly)
        for i in range(n - 1):  # poly는 첫점=끝점으로 이미 닫혀있다고 가정
            if _segments_intersect(rsu_xy, point_xy, tuple(poly[i]), tuple(poly[i + 1])):
                return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="건물 LOS 차단을 반영한 유효 커버리지 추정 (방법 A 확장: 순수거리 대비 LOS 필터링)"
    )
    parser.add_argument("--vehicle-csv", type=str, default=DEFAULT_VEHICLE_CSV)
    parser.add_argument("--candidates-csv", type=str, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--isolated-trend-csv", type=str, default=DEFAULT_ISOLATED_TREND_CSV)
    parser.add_argument("--poly-xml", type=str, default=DEFAULT_POLY_XML)
    parser.add_argument("--los-corr-out", type=str, default=OUTPUT_LOS_CORR_CSV)
    parser.add_argument("--rank-summary-out", type=str, default=OUTPUT_RANK_SUMMARY_CSV)
    parser.add_argument("--corr-plot-out", type=str, default=OUTPUT_CORR_PLOT_PNG)
    parser.add_argument("--scatter-plot-out", type=str, default=OUTPUT_SCATTER_PLOT_PNG)
    args = parser.parse_args()

    start = time.time()

    print(f"'{args.poly_xml}' 에서 건물 폴리곤 로딩 중...")
    buildings = load_buildings(args.poly_xml)
    print(f"✔ 건물 {len(buildings)}개 로딩 완료")
    b_tree, b_radii, b_max_radius = build_building_index(buildings)

    print(f"'{args.vehicle_csv}' 로딩 중...")
    veh_df = pd.read_csv(args.vehicle_csv)
    veh_points = np.column_stack([
        veh_df["x"].values - OFFSET_X,
        veh_df["y"].values - OFFSET_Y,
    ])
    print(f"✔ 차량 포인트 {len(veh_points)}개 로딩 완료")
    veh_tree = cKDTree(veh_points)

    candidates_df = pd.read_csv(args.candidates_csv)
    isolated_df = pd.read_csv(args.isolated_trend_csv)
    merged_meta = candidates_df.merge(isolated_df, on="Rank", how="inner")

    rank_rows = []
    threshold_los_counts = {d: [] for d in DISTANCE_THRESHOLDS}

    for _, row in merged_meta.iterrows():
        rank = int(row["Rank"])
        rsu_xy = (row["Sim_X"], row["Sim_Y"])

        # 150m 이내 차량 포인트만 우선 추려서 LOS 판정 대상 축소 (성능 최적화)
        nearby_idx = veh_tree.query_ball_point(rsu_xy, MAX_RADIUS)
        nearby_pts = veh_points[nearby_idx]
        dists = np.linalg.norm(nearby_pts - np.array(rsu_xy), axis=1)

        los_flags = np.array([
            has_line_of_sight(rsu_xy, tuple(pt), buildings, b_tree, b_radii, b_max_radius)
            for pt in nearby_pts
        ])

        total_150 = len(nearby_pts)
        los_150 = int(los_flags.sum())
        blocked_150 = total_150 - los_150

        rank_rows.append({
            "Rank": rank, "Total_within_150m": total_150,
            "LOS_within_150m": los_150, "Blocked_within_150m": blocked_150,
            "LOS_ratio": round(los_150 / total_150, 3) if total_150 else 0.0,
        })

        for d in DISTANCE_THRESHOLDS:
            count = int(np.sum((dists < d) & los_flags))
            threshold_los_counts[d].append(count)

        print(f"   [Rank {rank}] 150m 이내 {total_150}개 중 LOS(시야 확보) {los_150}개, "
              f"차단 {blocked_150}개 (LOS 비율 {los_150/total_150*100:.1f}%)"
              if total_150 else f"   [Rank {rank}] 150m 이내 포인트 없음")

    rank_summary_df = pd.DataFrame(rank_rows)
    rank_summary_df = rank_summary_df.merge(
        merged_meta[["Rank", "PDR_Mean", "Received_Mean"]], on="Rank", how="left"
    )
    rank_summary_df.to_csv(args.rank_summary_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" Rank별 150m 이내 전체/LOS(시야확보)/차단 개수 + 실제 단독 PDR")
    print("=" * 70)
    print(rank_summary_df.to_string(index=False))
    print("=" * 70)

    # ---------------------------------------------------------------
    # 거리 임계값별 "LOS 포인트 개수 vs 실제 PDR" 상관계수
    # ---------------------------------------------------------------
    full_df = merged_meta.copy()
    for d in DISTANCE_THRESHOLDS:
        full_df[f"los_count_within_{d}m"] = threshold_los_counts[d]

    corr_rows = []
    for d in DISTANCE_THRESHOLDS:
        col = f"los_count_within_{d}m"
        pearson_r, pearson_p = pearsonr(full_df[col], full_df["PDR_Mean"])
        spearman_r, spearman_p = spearmanr(full_df[col], full_df["PDR_Mean"])
        corr_rows.append({
            "Distance_m": d,
            "Pearson_r": round(pearson_r, 4), "Pearson_p": round(pearson_p, 4),
            "Spearman_r": round(spearman_r, 4), "Spearman_p": round(spearman_p, 4),
        })
    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(args.los_corr_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" 거리 임계값별 'LOS 포인트 수 vs 단독 PDR' 상관계수 (건물 차단 반영)")
    print("=" * 70)
    print(corr_df.to_string(index=False))
    print("=" * 70)

    best_row = corr_df.loc[corr_df["Pearson_r"].idxmax()]
    best_d = int(best_row["Distance_m"])
    print(f"\n✔ Pearson 상관계수가 가장 높은 거리 임계값: {best_d}m "
          f"(r={best_row['Pearson_r']}, p={best_row['Pearson_p']})")

    elapsed = time.time() - start
    print(f"\n[소요시간] 총 {elapsed/60:.1f}분")

    # ---------------------------------------------------------------
    # 그래프
    # ---------------------------------------------------------------
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(10, 6))
    plt.plot(corr_df["Distance_m"], corr_df["Pearson_r"], 'o-', color='seagreen', label='Pearson r (LOS-filtered)')
    plt.plot(corr_df["Distance_m"], corr_df["Spearman_r"], 's--', color='darkorange', label='Spearman r (LOS-filtered)')
    plt.axvline(best_d, color='red', linestyle=':', label=f'Best d={best_d}m')
    plt.xlabel("Distance Threshold d (m)", fontsize=13)
    plt.ylabel("Correlation with Isolated PDR", fontsize=13)
    plt.title("LOS-filtered Coverage Count vs Actual PDR, by Threshold d", fontsize=14, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='best')
    plt.tight_layout()
    plt.savefig(args.corr_plot_out, dpi=300)
    print(f"Saved LOS correlation-vs-distance chart to '{args.corr_plot_out}'.")
    plt.close()

    plt.figure(figsize=(9, 7))
    best_col = f"los_count_within_{best_d}m"
    plt.scatter(full_df[best_col], full_df["PDR_Mean"], color='teal', s=60)
    for _, row in full_df.iterrows():
        plt.annotate(str(int(row["Rank"])), (row[best_col], row["PDR_Mean"]),
                     textcoords="offset points", xytext=(5, 5), fontsize=8)
    plt.xlabel(f"LOS Vehicle Points within {best_d}m of RSU Candidate", fontsize=13)
    plt.ylabel("Isolated PDR (%)", fontsize=13)
    plt.title(f"Best-fit LOS-filtered Threshold ({best_d}m): LOS Points within d vs Actual PDR\n"
              f"(labels = candidate Rank)", fontsize=13, pad=20)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(args.scatter_plot_out, dpi=300)
    print(f"Saved LOS best-fit scatter chart to '{args.scatter_plot_out}'.")
    plt.close()


if __name__ == "__main__":
    main()
