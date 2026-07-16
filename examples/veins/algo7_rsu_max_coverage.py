"""
RSU (Roadside Unit) 위치 최적화 - Greedy Max Coverage Algorithm
================================================================

문제 정의:
  - SUMO 시뮬레이션에서 n번(예: 100회) 스냅샷을 찍어 차량 위치(50대 x n장 = 최대 5000개 점)를 수집
  - 후보 RSU 설치 위치(교차로 등) C 중에서 k개를 선택
  - 선택된 RSU들의 통신 반경(r=150m) 원이 커버하는 차량 포인트 수(중복 제거)를 최대화

알고리즘: Greedy Max Coverage (Maximum Coverage Location Problem, MCLP)
  - NP-hard 문제이지만, 커버리지 함수가 submodular하므로
    greedy 알고리즘은 최적해 대비 (1 - 1/e) ≈ 63% 근사 보장을 가짐
"""

import numpy as np
from scipy.spatial import cKDTree
import xml.etree.ElementTree as ET
from typing import List, Tuple
import argparse
import pandas as pd  # ID 매칭 및 파일 저장을 위해 추가


# ---------------------------------------------------------------------------
# 1. 데이터 로딩
# ---------------------------------------------------------------------------

def load_vehicle_points_from_fcd(fcd_path: str) -> np.ndarray:
    points = []
    for event, elem in ET.iterparse(fcd_path, events=("end",)):
        if elem.tag == "vehicle":
            x = float(elem.get("x"))
            y = float(elem.get("y"))
            points.append((x, y))
        if elem.tag == "timestep":
            elem.clear()

    if not points:
        raise ValueError(f"{fcd_path} 에서 차량 좌표를 찾을 수 없습니다.")
    return np.array(points)


def load_candidates_from_intersections(net_path: str, include_types: Tuple[str, ...] = None) -> np.ndarray:
    import sumolib
    net = sumolib.net.readNet(net_path)
    exclude = {"dead_end", "internal", "unregulated"}
    candidates = []
    for node in net.getNodes():
        ntype = node.getType()
        if include_types is not None:
            if ntype not in include_types:
                continue
        else:
            if ntype in exclude:
                continue
        x, y = node.getCoord()
        candidates.append((x, y))
    return np.array(candidates)


def load_points_from_csv(csv_path: str) -> np.ndarray:
    """차량 스냅샷(csv)에서 x, y가 3, 4번째 컬럼인 데이터를 로드합니다."""
    data = np.loadtxt(csv_path, delimiter=",", skiprows=1, usecols=(3, 4))
    return data

# ---------------------------------------------------------------------------
# 2. Greedy Max Coverage 알고리즘
# ---------------------------------------------------------------------------

def greedy_max_coverage(points: np.ndarray,
                         candidates: np.ndarray,
                         radius: float,
                         k: int,
                         verbose: bool = True) -> Tuple[np.ndarray, np.ndarray, float]:
    n_points = len(points)
    n_candidates = len(candidates)

    if k > n_candidates:
        raise ValueError(f"k({k})가 후보 개수({n_candidates})보다 큽니다.")

    tree = cKDTree(points)
    coverage_lists = tree.query_ball_point(candidates, radius)
    coverage_sets = [set(lst) for lst in coverage_lists]

    covered = set()
    selected_indices = []
    remaining_candidates = set(range(n_candidates))

    for step in range(k):
        best_idx, best_gain = -1, -1

        for i in remaining_candidates:
            gain = len(coverage_sets[i] - covered)
            if gain > best_gain:
                best_gain, best_idx = gain, i

        if best_gain <= 0:
            if verbose:
                print(f"[step {step+1}] 더 이상 커버할 새 포인트가 없어 조기 종료합니다.")
            break

        selected_indices.append(best_idx)
        covered |= coverage_sets[best_idx]
        remaining_candidates.remove(best_idx)

        if verbose:
            cum_ratio = len(covered) / n_points * 100
            print(f"[step {step+1:>2}] 후보지 idx={best_idx:<3} "
                  f"신규 커버={best_gain:<5} "
                  f"누적 커버율={cum_ratio:.1f}%")

    if not selected_indices:
        print("\n[!] 경고: 커버 가능한 차량이 0대입니다. (좌표계를 확인하세요)")
        return np.array([], dtype=int), np.array([]), 0.0

    selected_indices = np.array(selected_indices, dtype=int)
    selected_coords = candidates[selected_indices]
    coverage_ratio = len(covered) / n_points

    return selected_indices, selected_coords, coverage_ratio


# ---------------------------------------------------------------------------
# 3. 결과 시각화
# ---------------------------------------------------------------------------

def plot_result(points: np.ndarray,
                 candidates: np.ndarray,
                 selected_coords: np.ndarray,
                 radius: float,
                 save_path: str = "rsu_coverage_final.png"):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, ax = plt.subplots(figsize=(12, 10))

    # 1. 차량 위치
    ax.scatter(points[:, 0], points[:, 1], s=1, alpha=0.1, color='blue', label='Vehicle Snapshot')

    # 2. 교차로 후보지
    ax.scatter(candidates[:, 0], candidates[:, 1], s=15, color='gray', marker='^', alpha=0.3, label='Candidate Intersections')

    # 3. RSU 배치
    ax.scatter(selected_coords[:, 0], selected_coords[:, 1], s=200, color='red', 
               marker='X', edgecolors='white', linewidth=1.5, zorder=5, label='Optimal RSU Placement')

    # 4. 커버리지 원
    for cx, cy in selected_coords:
        circle = Circle((cx, cy), radius, fill=True, alpha=0.05, color="red", zorder=1)
        ax.add_patch(circle)
        edge = Circle((cx, cy), radius, fill=False, edgecolor="red", linewidth=1.2, zorder=2)
        ax.add_patch(edge)

    ax.set_aspect("equal")
    ax.set_title("Vehicle Scatter & Optimal RSU Placement (OMNeT++ Sim Coords)", fontsize=15)
    ax.set_xlabel("Sim_X Coordinate (m)")
    ax.set_ylabel("Sim_Y Coordinate (m)")
    ax.legend(loc='upper right')
    ax.grid(True, linestyle='--', alpha=0.3)
    
    # 여백 최소화
    ax.set_xlim(min(candidates[:, 0]) - 100, max(candidates[:, 0]) + 100)
    ax.set_ylim(min(candidates[:, 1]) - 100, max(candidates[:, 1]) + 100)

    plt.savefig(save_path, dpi=300)
    print(f"✔ 시각화 완료: '{save_path}' 파일이 생성되었습니다.")
    plt.show()


# ---------------------------------------------------------------------------
# 4. 메인 실행부
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RSU 위치 최적화 (Greedy Max Coverage)")
    parser.add_argument("--fcd", type=str, help="FCD output XML 경로 (차량 위치)")
    parser.add_argument("--csv", type=str, help="CSV 형태 차량 위치 (fcd 대신 사용 가능)")
    parser.add_argument("--net", type=str, help="SUMO net.xml 경로 (교차로 후보 자동 추출용)")
    parser.add_argument("--candidates-csv", type=str, help="이미 만들어둔 후보 좌표 CSV (net 대신 사용 가능)")
    parser.add_argument("--use-points-as-candidates", action="store_true")
    parser.add_argument("--radius", type=float, default=150.0, help="RSU 통신 반경 (m)")
    parser.add_argument("--k", type=int, default=5, help="설치할 RSU 개수")
    parser.add_argument("--plot", action="store_true", help="결과 시각화 여부")
    args = parser.parse_args()

    # --- 1. 차량 포인트 로딩 ---
    if args.fcd:
        points = load_vehicle_points_from_fcd(args.fcd)
    elif args.csv:
        points = load_points_from_csv(args.csv)
    else:
        raise SystemExit("--fcd 또는 --csv 중 하나는 반드시 지정해야 합니다.")

    print(f"차량 포인트 총 {len(points)}개 로딩 완료")

    # [좌표계 변환] UTM -> OMNeT++ 시뮬레이션 좌표
    OFFSET_X = 644465.09
    OFFSET_Y = 5491786.25
    points[:, 0] = points[:, 0] - OFFSET_X 
    points[:, 1] = points[:, 1] - OFFSET_Y 
    print("✔ 차량 좌표계를 OMNeT++ 로컬 시뮬레이션 좌표계(Sim_X, Sim_Y)로 변환 완료")

    # --- 2. 후보 위치 로딩 (ID 추출 로직 포함) ---
    if args.use_points_as_candidates:
        candidates = points.copy()
        candidate_ids = np.array([f"Point_{i}" for i in range(len(candidates))])
    elif args.net:
        candidates = load_candidates_from_intersections(args.net)
        candidate_ids = np.array([f"Intersection_{i}" for i in range(len(candidates))])
    elif args.candidates_csv:
        df_cand = pd.read_csv(args.candidates_csv)
        if 'ID' in df_cand.columns and 'Sim_X' in df_cand.columns and 'Sim_Y' in df_cand.columns:
            candidate_ids = df_cand['ID'].astype(str).values
            candidates = df_cand[['Sim_X', 'Sim_Y']].values
        else:
            candidates = load_points_from_csv(args.candidates_csv)
            candidate_ids = np.array([f"Cand_{i}" for i in range(len(candidates))])
    else:
        raise SystemExit("후보지 지정 옵션(--net, --candidates-csv 등)이 필요합니다.")

    print(f"후보 위치(교차로) 총 {len(candidates)}개 로딩 완료\n")

    # --- 3. Greedy Max Coverage 실행 ---
    print(f"=== Greedy Max Coverage 실행 (radius={args.radius}m, k={args.k}) ===")
    selected_idx, selected_coords, ratio = greedy_max_coverage(
        points, candidates, radius=args.radius, k=args.k
    )

    if len(selected_coords) > 0:
        print(f"\n최종 커버리지: {ratio*100:.2f}% ({int(ratio*len(points))}/{len(points)} 점)")
        print("\n=== 최종 선택된 RSU 정보 ===")
        
        # [추가] CSV로 저장할 리스트
        final_rsu_list = []
        
        for rank, idx in enumerate(selected_idx):
            rsu_id = candidate_ids[idx]
            x, y = selected_coords[rank]
            print(f"  Rank {rank+1} [ID: {rsu_id}]: (Sim_X: {x:.2f}, Sim_Y: {y:.2f})")
            
            final_rsu_list.append({
                "Rank": rank + 1,
                "ID": rsu_id,
                "Sim_X": round(x, 2),
                "Sim_Y": round(y, 2)
            })

        # [추가] 파일로 저장
        out_df = pd.DataFrame(final_rsu_list)
        out_filename = "final_selected_rsus.csv"
        out_df.to_csv(out_filename, index=False)
        print(f"\n✔ 결과가 '{out_filename}' 파일에 성공적으로 저장되었습니다.")

        if args.plot:
            plot_result(points, candidates, selected_coords, args.radius)


if __name__ == "__main__":
    main()
