# -*- coding: utf-8 -*-
"""
patch_beacon_offset.py
================================================================
DemoBaseApplLayer.ned / .cc 에 아래 두 가지를 패치하는 스크립트:
  1) avoidBeaconSynchronization=false일 때 scheduleAt()이 아예 호출 안
     되던 버그 수정 (블록 밖으로 이동)
  2) index 기반 결정론적 비콘 오프셋 파라미터(indexOffset) 추가
VM에서 실행: python3 patch_beacon_offset.py
"""
import os

NED_PATH = os.path.expanduser("~/veins/src/veins/modules/application/ieee80211p/DemoBaseApplLayer.ned")
CC_PATH = os.path.expanduser("~/veins/src/veins/modules/application/ieee80211p/DemoBaseApplLayer.cc")


def patch_ned():
    with open(NED_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "bool avoidBeaconSynchronization = default(true);"
    if marker not in content:
        print("!! NED: avoidBeaconSynchronization 줄을 못 찾았습니다. 수동 확인 필요.")
        return False

    if "indexOffset" in content:
        print("-- NED: indexOffset이 이미 있습니다. 건너뜁니다.")
        return True

    lines = content.split("\n")
    new_lines = []
    for line in lines:
        new_lines.append(line)
        if marker in line:
            new_lines.append(
                "        double indexOffset @unit(s) = default(0s); "
                "// [algo7] index 기반 결정론적 비콘 시작 오프셋 "
                "(예: *.rsu[*].appl.indexOffset = (index * 0.01)s), 0이면 영향 없음"
            )
    new_content = "\n".join(new_lines)

    with open(NED_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("OK NED 패치 완료")
    return True


def patch_cc():
    with open(CC_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "indexOffset" in content:
        print("-- CC: indexOffset이 이미 있습니다. 건너뜁니다.")
        return True

    old_block = '''        simtime_t firstBeacon = simTime();

        if (par("avoidBeaconSynchronization").boolValue() == true) {

            simtime_t randomOffset = dblrand() * beaconInterval;
            firstBeacon = simTime() + randomOffset;

            if (mac->isChannelSwitchingActive() == true) {
                if (beaconInterval.raw() % (mac->getSwitchingInterval().raw() * 2)) {
                    EV_ERROR << "The beacon interval (" << beaconInterval << ") is smaller than or not a multiple of  one synchronization interval (" << 2 * mac->getSwitchingInterval() << "). This means that beacons are generated during SCH intervals" << std::endl;
                }
                firstBeacon = computeAsynchronousSendingTime(beaconInterval, ChannelType::control);
            }

            if (sendBeacons) {
                scheduleAt(firstBeacon, sendBeaconEvt);
            }
        }'''

    new_block = '''        simtime_t firstBeacon = simTime();

        if (par("avoidBeaconSynchronization").boolValue() == true) {

            simtime_t randomOffset = dblrand() * beaconInterval;
            firstBeacon = simTime() + randomOffset;

            if (mac->isChannelSwitchingActive() == true) {
                if (beaconInterval.raw() % (mac->getSwitchingInterval().raw() * 2)) {
                    EV_ERROR << "The beacon interval (" << beaconInterval << ") is smaller than or not a multiple of  one synchronization interval (" << 2 * mac->getSwitchingInterval() << "). This means that beacons are generated during SCH intervals" << std::endl;
                }
                firstBeacon = computeAsynchronousSendingTime(beaconInterval, ChannelType::control);
            }
        }
        // [algo7] 버그 수정: 원래 scheduleAt()이 avoidBeaconSynchronization==true
        // 블록 안에만 있어서, false로 설정하면 비콘이 아예 발신되지 않았음(총 발신 0).
        // false일 때도 (오프셋 없이) 비콘이 나가도록 블록 밖으로 뺌.
        // 추가로 indexOffset(결정론적 인덱스 기반 오프셋)을 무조건 더해줌.
        firstBeacon += par("indexOffset").doubleValueInUnit("s");
        if (sendBeacons) {
            scheduleAt(firstBeacon, sendBeaconEvt);
        }'''

    if old_block not in content:
        print("!! CC: 원본 블록을 정확히 못 찾았습니다. 수동 확인이 필요합니다.")
        return False

    content = content.replace(old_block, new_block)
    with open(CC_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK CC 패치 완료")
    return True


if __name__ == "__main__":
    ok1 = patch_ned()
    ok2 = patch_cc()
    if ok1 and ok2:
        print("\n두 파일 모두 패치 완료. 이제 재컴파일해야 합니다.")
    else:
        print("\n!! 일부 패치 실패. 파일을 직접 확인해주세요.")
