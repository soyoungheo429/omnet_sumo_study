# -*- coding: utf-8 -*-
"""
rsu_lib/config_version.py
================================================================
omnetpp_template.ini는 실행마다 계속 덮어써지기 때문에, 예전에 "bitrate를
27Mbps로 바꿨다가 다시 6Mbps로 돌아가서 뭐가 뭔지 헷갈렸던" 문제가 있었다.

좌표(RSU 위치)는 매 실행 다르므로 버전화할 필요 없지만, bitrate/동기화
여부 같은 "이 실험의 조건(regime)"은 한 번 쓴 조합이 사라지지 않도록
configs/versions/ 에 이름 붙여서 스냅샷으로 남긴다.
================================================================
"""

import os
import re

VERSIONS_DIR = "configs/versions"


def _extract_regime(ini_content: str) -> dict:
    bitrate_m = re.search(
        r"\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=\s*([\w.]+)", ini_content
    )
    sync_m = re.search(
        r"\*\.rsu\[\*\]\.appl\.avoidBeaconSynchronization\s*=\s*(true|false)",
        ini_content,
    )
    return {
        "bitrate": bitrate_m.group(1) if bitrate_m else "unknown",
        "sync": sync_m.group(1) if sync_m else "unknown",
    }


def snapshot_current_regime(template_path: str = "omnetpp_template.ini") -> str:
    """지금 omnetpp_template.ini의 bitrate/sync 조합을 configs/versions/에
    영구 저장한다. 같은 조합이 이미 있으면 덮어쓰지 않고 그대로 재사용
    (좌표 등 매번 바뀌는 부분은 애초에 이 템플릿에 안 들어있으므로 안전)."""
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    regime = _extract_regime(content)
    version_name = f"bitrate{regime['bitrate']}_sync{regime['sync'].capitalize()}.ini"
    version_path = os.path.join(VERSIONS_DIR, version_name)

    if not os.path.exists(version_path):
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[config_version] 새 조합 저장: {version_path}")
    else:
        print(f"[config_version] 이미 존재하는 조합, 건너뜀: {version_path}")

    return version_path


def list_known_versions() -> list:
    if not os.path.isdir(VERSIONS_DIR):
        return []
    return sorted(os.listdir(VERSIONS_DIR))


if __name__ == "__main__":
    path = snapshot_current_regime()
    print("현재까지 저장된 조합들:", list_known_versions())
