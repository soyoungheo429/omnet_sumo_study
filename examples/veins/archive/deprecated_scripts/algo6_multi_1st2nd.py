import os
import subprocess
import shutil
import re

# 설정값
RUN_SCRIPT = "./run"
INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RESULT_DIR = "results"

# GA로 찾은 최적 좌표
RSU1_COORD = (1306.06, 1348.74)
RSU2_COORD = (1307.27, 1348.41)

def run_2rsu_simulation():
    if os.path.exists(RESULT_DIR):
        shutil.rmtree(RESULT_DIR, ignore_errors=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    with open(INI_TEMPLATE, "r") as f:
        content = f.read()

    # 1. numRSUs 개수 변경 (강제 대체)
    content = re.sub(r"\*\.numRSUs\s*=\s*\d+", "*.numRSUs = 2", content)
    
    # 2. RSU 설정 블록 작성
    rsu_config = f"""
# --- 자동 생성된 RSU 설정 ---
*.rsu[0].mobility.typename = "StationaryMobility"
*.rsu[0].mobility.x = {RSU1_COORD[0]:.2f}
*.rsu[0].mobility.y = {RSU1_COORD[1]:.2f}
*.rsu[0].mobility.z = 3
*.rsu[1].mobility.typename = "StationaryMobility"
*.rsu[1].mobility.x = {RSU2_COORD[0]:.2f}
*.rsu[1].mobility.y = {RSU2_COORD[1]:.2f}
*.rsu[1].mobility.z = 3
*.rsu[*].applType = "TraCIDemoRSU11p"
*.rsu[*].appl.sendBeacons = true
# ---------------------------
"""
    # 3. [General] 섹션 바로 아래에 설정을 삽입 (중복 방지)
    if "[General]" in content:
        content = content.replace("[General]", "[General]" + rsu_config)
    else:
        content = rsu_config + content

    with open(WORKING_INI, "w") as f:
        f.write(content)

    print(f" >>> [실행] RSU 2대 배치 테스트 시작...")
    print(f"     RSU[0]: {RSU1_COORD} / RSU[1]: {RSU2_COORD}")
    
    # -c WithBeaconing 대신 General로 실행해도 위에서 설정을 덮어썼으므로 정상 작동함
    result = subprocess.run([RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"], 
                             capture_output=True, text=True)
    
    # 에러 확인용
    if result.returncode != 0:
        print("!! 시뮬레이션 실행 중 오류 발생 !!")
        print(result.stderr)
        
    return parse_multi_pdr()

def parse_multi_pdr():
    result_path = os.path.join(RESULT_DIR, "General-#0.sca")
    if not os.path.exists(result_path): 
        print("!! 결과 파일이 생성되지 않았습니다 (results 폴더 확인) !!")
        return 0.0
    
    try:
        with open(result_path, "r") as f:
            content = f.read()
            # 모든 RSU(0, 1) 발신량 합산
            total_gen = sum(int(n) for n in re.findall(r"rsu\[\d+\].appl\s+generatedBSMs\s+(\d+)", content))
            # 모든 노드 수신량 합산
            nodes = re.findall(r"node\[\d+\].appl\s+receivedBSMs\s+(\d+)", content)
            total_recv = sum(int(n) for n in nodes)
            
        print(f"   [분석] 총 발신: {total_gen}, 총 수신: {total_recv}")
        return (total_recv / (total_gen * 50)) * 100 if total_gen > 0 else 0.0
    except Exception as e:
        print(f"!! 파싱 중 오류: {e} !!")
        return 0.0

# 메인 실행
pdr = run_2rsu_simulation()
print(f"\n==========================================")
print(f"결과: 2대 배치 시 최종 PDR = {pdr:.2f}%")
print(f"==========================================")
