import os
import subprocess
import pandas as pd
import re
import shutil

RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"
CSV_FILE = "final_selected_rsus_k5.csv"  # 소영님이 말씀하신 파일명

def run_verified_simulation():
    if not os.path.exists(CSV_FILE):
        print(f"!! 에러: '{CSV_FILE}' 파일이 없습니다 !!")
        return

    # CSV 로드
    df = pd.read_csv(CSV_FILE)
    print(f"✔ '{CSV_FILE}'에서 {len(df)}개 RSU 좌표 로딩 완료.")

    # 템플릿 읽기 및 설정
    with open(INI_TEMPLATE, "r") as f:
        content = f.read()

    # numRSUs 동적 변경
    content = re.sub(r"\*\.numRSUs\s*=\s*\d+", f"*.numRSUs = {len(df)}", content)
    
    # RSU 설정 문자열 생성
    rsu_config = "\n# --- 자동 생성된 최적화 RSU 배치 ---\n"
    for i, row in df.iterrows():
        rsu_config += f"*.rsu[{i}].mobility.typename = \"StationaryMobility\"\n"
        rsu_config += f"*.rsu[{i}].mobility.x = {row['Sim_X']}\n"
        rsu_config += f"*.rsu[{i}].mobility.y = {row['Sim_Y']}\n"
        rsu_config += f"*.rsu[{i}].mobility.z = 3\n"
        rsu_config += f"*.rsu[{i}].applType = \"TraCIDemoRSU11p\"\n"
        rsu_config += f"*.rsu[{i}].appl.sendBeacons = true\n"
    rsu_config += "# ------------------------------------\n"
    
    # [General] 섹션 아래에 삽입
    if "[General]" in content:
        content = content.replace("[General]", "[General]" + rsu_config)
    
    with open(WORKING_INI, "w") as f:
        f.write(content)

    # 시뮬레이션 실행
    if os.path.exists(RESULT_DIR): shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    print(" >>> [실행] 최적 RSU 5대 배치 시뮬레이션 시작...")
    subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], check=True)
    
    # PDR 파싱
    calculate_pdr()

def calculate_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    with open(result_path, "r") as f:
        content = f.read()
        total_gen = sum(int(n) for n in re.findall(r"rsu\[\d+\].appl\s+generatedBSMs\s+(\d+)", content))
        total_recv = sum(int(n) for n in re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content))
        
    print("\n" + "="*40)
    print(f"🚀 최적 배치(K=5) 시 최종 PDR = {(total_recv / (total_gen * 50)) * 100:.2f}%")
    print("="*40)

if __name__ == "__main__":
    run_verified_simulation()
