import os
import subprocess
import pandas as pd
import itertools
import re
import shutil

# =========================================================
# 1. 설정값
# =========================================================
# [algo7] 좌표 보정 완료된 algo1의 27개 후보 + 단독 PDR (Sim_X/Sim_Y는 이미
# traci2omnet() 보정 적용됨 - 이 스크립트 자체는 추가 변환이 필요 없음,
# 예전 버전의 문제는 입력 CSV의 좌표가 보정 안 돼 있었던 것뿐이었음)
ALGO1_RESULT_CSV = "algo1_single_pdr_for_algo5.csv"
TOP_N = 27  # 27개 전체 사용 -> 27C2 = 351개 조합 (원본은 40개/780조합이었으나 보정된 후보가 27개뿐)
K_RSUS = 2

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
FINAL_CSV = f"algo5_baseline_top{TOP_N}_c{K_RSUS}_results_corrected.csv"

# =========================================================
# 2. 상위 TOP_N개 교차로 로드 및 조합 생성
# =========================================================
if not os.path.exists(ALGO1_RESULT_CSV):
    print(f"오류: {ALGO1_RESULT_CSV} 파일이 없습니다.")
    exit()

df_single = pd.read_csv(ALGO1_RESULT_CSV)
df_top = df_single.sort_values(by="PDR", ascending=False).head(TOP_N)

candidates = []
for idx, row in df_top.iterrows():
    node_id = row["ID"] if "ID" in row else f"Node_{idx}"
    candidates.append(
        {"id": node_id, "x": row["Sim_X"], "y": row["Sim_Y"], "single_pdr": row["PDR"]}
    )

combinations_all = list(itertools.combinations(candidates, K_RSUS))

print("=" * 60)
print(
    f"상위 {TOP_N}개 교차로 로드 완료 (단독 PDR {df_top['PDR'].min():.2f}% ~ {df_top['PDR'].max():.2f}%, 좌표보정 적용됨)"
)
print(f"총 {len(combinations_all)}개의 시뮬레이션(조합)을 실행합니다.")
print("=" * 60)


# =========================================================
# 3. 시뮬레이션 및 파싱 함수
# =========================================================
def parse_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path):
        return 0.0

    try:
        total_received, rsu_generated, node_count = 0, 0, 0
        with open(result_path, "r") as f:
            content = f.read()

            rsu_gen_matches = re.findall(
                r"rsu\[\d+\].appl\s+generatedBSMs\s+(\d+)", content
            )
            rsu_generated = sum(int(val) for val in rsu_gen_matches)

            node_recv_matches = re.findall(
                r"node\[(\d+)\].appl\s+receivedBSMs\s+(\d+)", content
            )
            nodes = set()
            for node_idx, val in node_recv_matches:
                total_received += int(val)
                nodes.add(node_idx)
            node_count = len(nodes)

        num_vehicles = node_count if node_count > 0 else 50
        expected_total = rsu_generated * num_vehicles
        if expected_total == 0:
            return 0.0
        return (total_received / expected_total) * 100
    except Exception:
        return 0.0


def run_simulation(rsu1, rsu2):
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()

    multi_rsu_config = (
        f"\n\n# --- Baseline {K_RSUS}개 RSU 자동 생성 (좌표보정 적용) ---\n"
    )
    multi_rsu_config += f"*.numRSUs = {K_RSUS}\n"

    multi_rsu_config += f"*.rsu[0].mobility.x = {rsu1['x']:.2f}\n"
    multi_rsu_config += f"*.rsu[0].mobility.y = {rsu1['y']:.2f}\n"
    multi_rsu_config += f"*.rsu[1].mobility.x = {rsu2['x']:.2f}\n"
    multi_rsu_config += f"*.rsu[1].mobility.y = {rsu2['y']:.2f}\n"
    multi_rsu_config += "*.rsu[*].mobility.z = 3\n"
    multi_rsu_config += '*.rsu[*].applType = "TraCIDemoRSU11p"\n'
    multi_rsu_config += "*.rsu[*].appl.sendBeacons = true\n"

    content = content.replace("[General]", "[General]" + multi_rsu_config, 1)

    with open(WORKING_INI, "w") as f:
        f.write(content)

    process = subprocess.run(
        [RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], capture_output=True, text=True
    )

    if (
        process.returncode != 0
        or "<!> Error" in process.stderr
        or "<!> Error" in process.stdout
    ):
        print(f"\n시뮬레이션 에러 발생!\n{process.stderr}\n{process.stdout}")
        return 0.0
    return parse_pdr()


# =========================================================
# 4. 메인 루프 실행
# =========================================================
if __name__ == "__main__":
    results = []

    for idx, (rsu1, rsu2) in enumerate(combinations_all):
        print(
            f"[{idx + 1}/{len(combinations_all)}] {rsu1['id']} & {rsu2['id']} 조합 테스트 중...",
            end=" ",
        )

        combined_pdr = run_simulation(rsu1, rsu2)

        results.append(
            {
                "Combo_ID": f"Combo_{idx + 1}",
                "RSU1_ID": rsu1["id"],
                "RSU1_X": rsu1["x"],
                "RSU1_Y": rsu1["y"],
                "RSU1_Single_PDR": rsu1["single_pdr"],
                "RSU2_ID": rsu2["id"],
                "RSU2_X": rsu2["x"],
                "RSU2_Y": rsu2["y"],
                "RSU2_Single_PDR": rsu2["single_pdr"],
                "Combined_PDR": combined_pdr,
            }
        )
        print(f"-> 통합 PDR: {combined_pdr:.2f}%")

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="Combined_PDR", ascending=False)
    df_results.to_csv(FINAL_CSV, index=False)

    print("\n" + "=" * 60)
    print(
        f"{len(combinations_all)}개 조합 테스트 완료! '{FINAL_CSV}'에 저장되었습니다."
    )
    best_combo = df_results.iloc[0]
    print(
        f"1등 조합: {best_combo['RSU1_ID']} & {best_combo['RSU2_ID']} -> PDR {best_combo['Combined_PDR']:.2f}%"
    )
    print("=" * 60)
