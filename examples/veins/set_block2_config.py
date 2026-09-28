import re

INI_PATH = "omnetpp_template.ini"

with open(INI_PATH, "r", encoding="utf-8") as f:
    content = f.read()

before = content

content, n1 = re.subn(
    r"^\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=.*$",
    "*.**.nic.mac1609_4.bitrate = 6Mbps  # [algo7] Block 2: 6Mbps + 좌표계보정",
    content, flags=re.MULTILINE,
)
content, n2 = re.subn(
    r"^\*\.rsu\[\*\]\.appl\.avoidBeaconSynchronization\s*=.*$",
    "*.rsu[*].appl.avoidBeaconSynchronization = true  # [algo7] Block 2: 기본(제비뽑기)",
    content, flags=re.MULTILINE,
)

print("bitrate 줄 치환:", n1, "건")
print("avoidBeaconSynchronization 줄 치환:", n2, "건")

if content == before:
    print("경고: 파일 내용이 전혀 안 바뀌었습니다.")
else:
    with open(INI_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("파일에 저장했습니다.")

print("")
print("저장 후 확인:")
for line in content.splitlines():
    if "bitrate" in line or "avoidBeaconSynchronization" in line:
        print(line)
