import subprocess

INI_TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
RUN_SCRIPT = "./run"

print("="*50)
print("👀 다중 RSU(K=2) GUI 시각적 확인을 시작합니다!")
print("="*50)

# 1. 템플릿 읽기
with open(INI_TEMPLATE, "r") as f:
    content = f.read()

# 2. 확실하게 떨어져 있는 2개의 좌표 강제 주입
# (눈으로 2개가 구별되게 멀리 떨어뜨려 놓았습니다)
multi_rsu_config = f"\n# --- GUI 시각적 확인용 RSU 2대 ---\n"
multi_rsu_config += f"*.numRSUs = 2\n"
multi_rsu_config += f"*.rsu[0].mobility.x = 500.00\n"
multi_rsu_config += f"*.rsu[0].mobility.y = 500.00\n"
multi_rsu_config += f"*.rsu[1].mobility.x = 2000.00\n"
multi_rsu_config += f"*.rsu[1].mobility.y = 2000.00\n"
multi_rsu_config += "*.rsu[*].mobility.z = 3\n"

content = content.replace("[General]", "[General]" + multi_rsu_config)

# 3. omnetpp.ini 덮어쓰기
with open(WORKING_INI, "w") as f:
    f.write(content)

print("✅ 좌표 세팅 완료! OMNeT++ GUI 창이 열립니다...")
print("창이 열리면 상단의 [Run(재생 버튼)]을 눌러 RSU 2대가 있는지 확인하세요.")

# 4. 💥 Cmdenv(터미널) 대신 Qtenv(GUI) 모드로 실행!
subprocess.run([RUN_SCRIPT, "-u", "Qtenv", "-c", "General"])
