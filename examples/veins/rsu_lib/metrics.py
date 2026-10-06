# -*- coding: utf-8 -*-
"""
rsu_lib/metrics.py
================================================================
논문용 다중 지표 파서. results/General-#0.sca 하나에서 아래를 전부 계산한다.
(C++ 계측: src/veins/modules/application/traci/TraCIDemo11p.cc 의 [metrics] 블록)

  PDR(%)                 기존 정의 그대로: ΣRx / (ΣGen_RSU × N)      ← 기존 결과와 비교 가능
  Total_Received         ΣRx (차량들이 받은 BSM 총량)
  Service_Ratio(%)       차량 관점 서비스율: 0.1초 슬롯 중 BSM을 ≥1개 받은 슬롯 비율
                         = Σ uniqueRxSlots / Σ (aliveTime / 0.1)
                         → K가 늘수록 "덮이는 시간"이 늘면 증가 (희석 없음)
  Jain_RSU               RSU 간 부하 공평도  J = (Σx)^2 / (n·Σx^2), x_i = RSU i가 전달한 BSM 수
                         (수신자가 0명인 RSU도 x=0으로 포함 → 놀고 있는 RSU가 있으면 J 하락)
  Jain_Vehicle           차량 간 서비스 공평도, x_j = 차량 j의 수신 BSM 수
  PER(%)                 차량 MAC 기준 프레임 에러율 = SNIRLost / (ReceivedBroadcasts + SNIRLost)
                         (SNIRLost = 비트에러 + 충돌로 디코딩 실패한 프레임)
  Collisions             차량 PHY의 ncollisions 합 (간섭만 없었으면 성공했을 프레임)
  RXTX_Lost              송신 중 수신이라 놓친 프레임 (차량은 비콘을 안 보내 ~0이 정상)
  RSSI_Mean_dBm          성공 수신 BSM의 평균 수신 세기 (dBm 평균)
  SNR_Mean_dB            성공 수신 BSM의 평균 SNR
  Channel_Busy(%)        차량 PHY busyTime 평균 (채널 점유율)
  PerRSU_Rx              RSU별 전달 BSM 수 (JSON 문자열, rsu index 순서)
                         → 단독 실험 결과와 비교하면 RSU별 간섭 손실을 직접 계산 가능

PER/RSSI의 분모 주의: RSSI는 "성공 수신"만 평균이라 낙관 편향이 있음(논문에 명시).
================================================================
"""
import json
import math
import os
import re

SLOT_SEC = 0.1  # C++ METRIC_SLOT_SEC 과 반드시 같게

# OMNeT++ .sca:  scalar <module> <name> <value>   (module/name에 공백 있으면 "..." 로 감싸짐)
_RE_SCALAR = re.compile(r'^scalar\s+("(?:[^"\\]|\\.)*"|\S+)\s+("(?:[^"\\]|\\.)*"|\S+)\s+(\S+)\s*$')
_RE_NODE = re.compile(r"\.node\[(\d+)\]\.(.+)$")
_RE_RSU = re.compile(r"\.rsu\[(\d+)\]\.(.+)$")


def _unq(s):
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s


def read_scalars(sca_path):
    """반환: [(module, name, float_value), ...]"""
    out = []
    with open(sca_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("scalar"):
                continue
            m = _RE_SCALAR.match(line.rstrip("\n"))
            if not m:
                continue
            try:
                v = float(m.group(3))
            except ValueError:
                v = float("nan")
            out.append((_unq(m.group(1)), _unq(m.group(2)), v))
    return out


def jain(xs):
    xs = [float(x) for x in xs]
    n = len(xs)
    s2 = sum(x * x for x in xs)
    if n == 0 or s2 == 0:
        return float("nan")
    return (sum(xs) ** 2) / (n * s2)


def _match_rsu_keys(pos_counts, rsu_coords, tol=2.0):
    """'x_y' 키를 ini에 넣은 rsu 좌표와 매칭 → rsu index별 수신량 리스트. 실패하면 None."""
    if not rsu_coords:
        return None
    per = [0.0] * len(rsu_coords)
    unmatched = 0
    for key, cnt in pos_counts.items():
        try:
            kx, ky = (float(t) for t in key.split("_"))
        except ValueError:
            unmatched += cnt
            continue
        d = [math.hypot(kx - x, ky - y) for (x, y) in rsu_coords]
        i = min(range(len(d)), key=d.__getitem__)
        if d[i] <= tol:
            per[i] += cnt
        else:
            unmatched += cnt
    total = sum(pos_counts.values())
    # 좌표 키가 RSU 수보다 적게 뭉쳐 있거나(예: 전부 0_0), 매칭 실패가 많으면 신뢰 불가
    if total == 0 or unmatched > 0.01 * total:
        return None
    return per


def parse_metrics(sca_path, rsu_coords=None):
    """rsu_coords: ini에 넣은 [(x, y), ...] (rsu index 순서). 없으면 PerRSU는 MAC 기준(순서 무의미)."""
    nan = float("nan")
    res = {
        "PDR": 0.0, "Total_Generated": 0, "Num_Vehicles": 0, "Num_RSUs": 0,
        "Total_Received": 0, "Service_Ratio": nan, "Jain_RSU": nan, "Jain_Vehicle": nan,
        "PER": nan, "Collisions": 0, "RXTX_Lost": 0, "RSSI_Mean_dBm": nan, "SNR_Mean_dB": nan,
        "Channel_Busy": nan, "PerRSU_Rx": "[]", "PerRSU_Source": "none", "Metrics_OK": False,
    }
    if not os.path.exists(sca_path):
        return res

    node = {}  # idx -> dict(name->value)   (appl/mac/phy 이름이 안 겹쳐서 하나로 합침, phy는 접두사)
    rsu_gen = {}
    for module, name, v in read_scalars(sca_path):
        m = _RE_NODE.search(module)
        if m:
            idx, sub = int(m.group(1)), m.group(2)
            d = node.setdefault(idx, {})
            if sub.endswith("appl"):
                d[name] = d.get(name, 0) + v
            elif "mac1609_4" in sub:
                d["mac." + name] = v
            elif "phy80211p" in sub:
                d["phy." + name] = v
            continue
        m = _RE_RSU.search(module)
        if m and m.group(2).endswith("appl") and name == "generatedBSMs":
            rsu_gen[int(m.group(1))] = v

    vehicles = [d for d in node.values() if "receivedBSMs" in d]
    N = len(vehicles)
    K = len(rsu_gen) if rsu_gen else (len(rsu_coords) if rsu_coords else 0)
    gen = sum(rsu_gen.values())
    rx = sum(d["receivedBSMs"] for d in vehicles)
    res.update(Total_Generated=int(gen), Num_Vehicles=N, Num_RSUs=K, Total_Received=int(rx))
    res["PDR"] = round(rx / (gen * N) * 100, 4) if gen > 0 and N > 0 else 0.0
    res["Jain_Vehicle"] = jain([d["receivedBSMs"] for d in vehicles])

    # --- MAC/PHY ---
    snir = sum(d.get("mac.SNIRLostPackets", 0) for d in vehicles)
    bc = sum(d.get("mac.ReceivedBroadcasts", 0) for d in vehicles)
    res["PER"] = round(snir / (bc + snir) * 100, 4) if (bc + snir) > 0 else nan
    res["RXTX_Lost"] = int(sum(d.get("mac.RXTXLostPackets", 0) for d in vehicles))
    res["Collisions"] = int(sum(d.get("phy.ncollisions", 0) for d in vehicles))
    busy = [d["phy.busyTime"] for d in vehicles if "phy.busyTime" in d]
    res["Channel_Busy"] = round(sum(busy) / len(busy) * 100, 4) if busy else nan

    # --- C++ [metrics] 계측값 ---
    has_metrics = any("metricRxMeasured" in d for d in vehicles)
    res["Metrics_OK"] = has_metrics
    if has_metrics:
        meas = sum(d.get("metricRxMeasured", 0) for d in vehicles)
        if meas > 0:
            res["RSSI_Mean_dBm"] = round(sum(d.get("metricRssiSum_dBm", 0) for d in vehicles) / meas, 3)
            res["SNR_Mean_dB"] = round(sum(d.get("metricSnrSum_dB", 0) for d in vehicles) / meas, 3)
        slots = sum(d.get("metricUniqueRxSlots", 0) for d in vehicles)
        alive_slots = sum(d.get("metricAliveTime", 0) / SLOT_SEC for d in vehicles)
        res["Service_Ratio"] = round(slots / alive_slots * 100, 4) if alive_slots > 0 else nan

        pos, mac = {}, {}
        for d in vehicles:
            for k, v in d.items():
                if k.startswith("metricRxFromMac_"):
                    mac[k[len("metricRxFromMac_"):]] = mac.get(k[len("metricRxFromMac_"):], 0) + v
                elif k.startswith("metricRxFrom_"):
                    pos[k[len("metricRxFrom_"):]] = pos.get(k[len("metricRxFrom_"):], 0) + v
        per = _match_rsu_keys(pos, rsu_coords)
        if per is not None:
            res["PerRSU_Source"] = "position"
        else:
            # 좌표 매칭 실패 → MAC 주소 기준 (RSU 순서는 알 수 없지만 Jain 계산에는 충분)
            per = sorted(mac.values(), reverse=True)
            per += [0.0] * max(0, K - len(per))
            res["PerRSU_Source"] = "mac"
        res["PerRSU_Rx"] = json.dumps([int(x) for x in per])
        res["Jain_RSU"] = round(jain(per), 4) if K > 1 else 1.0
    res["Jain_Vehicle"] = round(res["Jain_Vehicle"], 4) if res["Jain_Vehicle"] == res["Jain_Vehicle"] else nan
    return res


def interference_loss(multi_rx, isolated_rx_list):
    """η = 1 − Rx_multi / Σ Rx_isolated(i).  ≈0 이면 간섭 손실 없음."""
    s = sum(isolated_rx_list)
    return 1 - multi_rx / s if s > 0 else float("nan")
