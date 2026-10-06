# -*- coding: utf-8 -*-
"""rsu_lib/metrics.py 자체 검증 (가짜 .sca로). 실행: python3 -m rsu_lib.test_metrics"""
import json
import math
import os
import tempfile

from rsu_lib import metrics

SCA = """version 3
run General-0-20261006
attr configname General
attr network RSUExampleScenario

scalar RSUExampleScenario.rsu[0].appl generatedBSMs 2000
scalar RSUExampleScenario.rsu[1].appl generatedBSMs 2000
scalar RSUExampleScenario.rsu[2].appl generatedBSMs 2000
scalar RSUExampleScenario.node[0].appl receivedBSMs 300
scalar RSUExampleScenario.node[0].appl metricRxMeasured 300
scalar RSUExampleScenario.node[0].appl metricRssiSum_dBm -24000
scalar RSUExampleScenario.node[0].appl metricSnrSum_dB 6000
scalar RSUExampleScenario.node[0].appl metricUniqueRxSlots 250
scalar RSUExampleScenario.node[0].appl metricAliveTime 100
scalar RSUExampleScenario.node[0].appl metricRxFrom_1316_1268 200
scalar RSUExampleScenario.node[0].appl metricRxFrom_1586_1164 100
scalar RSUExampleScenario.node[0].appl metricRxFromMac_16 200
scalar RSUExampleScenario.node[0].appl metricRxFromMac_22 100
scalar RSUExampleScenario.node[0].nic.mac1609_4 ReceivedBroadcasts 300
scalar RSUExampleScenario.node[0].nic.mac1609_4 SNIRLostPackets 100
scalar RSUExampleScenario.node[0].nic.mac1609_4 RXTXLostPackets 0
scalar RSUExampleScenario.node[0].nic.phy80211p ncollisions 7
scalar RSUExampleScenario.node[0].nic.phy80211p busyTime 0.2
scalar RSUExampleScenario.node[1].appl receivedBSMs 100
scalar RSUExampleScenario.node[1].appl metricRxMeasured 100
scalar RSUExampleScenario.node[1].appl metricRssiSum_dBm -9000
scalar RSUExampleScenario.node[1].appl metricSnrSum_dB 1000
scalar RSUExampleScenario.node[1].appl metricUniqueRxSlots 50
scalar RSUExampleScenario.node[1].appl metricAliveTime 50
scalar RSUExampleScenario.node[1].appl metricRxFrom_1316_1268 100
scalar RSUExampleScenario.node[1].appl metricRxFromMac_16 100
scalar RSUExampleScenario.node[1].nic.mac1609_4 ReceivedBroadcasts 100
scalar RSUExampleScenario.node[1].nic.mac1609_4 SNIRLostPackets 0
scalar RSUExampleScenario.node[1].nic.phy80211p ncollisions 3
scalar RSUExampleScenario.node[1].nic.phy80211p busyTime 0.4
"""
COORDS = [(1315.6, 1268.14), (1585.98, 1164.28), (465.02, 1217.39)]


def close(a, b, eps=1e-3):
    return abs(a - b) < eps


def main():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.sca")
        open(p, "w").write(SCA)
        r = metrics.parse_metrics(p, COORDS)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        assert r["Num_Vehicles"] == 2 and r["Num_RSUs"] == 3
        assert r["Total_Received"] == 400
        assert close(r["PDR"], 400 / (6000 * 2) * 100)
        assert json.loads(r["PerRSU_Rx"]) == [300, 100, 0] and r["PerRSU_Source"] == "position"
        assert close(r["Jain_RSU"], metrics.jain([300, 100, 0]))  # 0.5
        assert close(r["Jain_Vehicle"], metrics.jain([300, 100]))  # 0.8
        assert close(r["PER"], 100 / 500 * 100)
        assert r["Collisions"] == 10
        assert close(r["RSSI_Mean_dBm"], -33000 / 400)
        assert close(r["Service_Ratio"], 300 / 1500 * 100)
        assert close(r["Channel_Busy"], 30.0)
        # 좌표 키가 깨진 경우 → MAC 기준으로 폴백
        r2 = metrics.parse_metrics(p, [(0, 0), (1, 1), (2, 2)])
        assert r2["PerRSU_Source"] == "mac" and json.loads(r2["PerRSU_Rx"]) == [300, 100, 0]
        assert close(metrics.interference_loss(90, [50, 50]), 0.1)
        assert math.isnan(metrics.jain([0, 0]))
    print("\nALL OK")


if __name__ == "__main__":
    main()
