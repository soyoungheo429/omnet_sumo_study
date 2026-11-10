# -*- coding: utf-8 -*-
"""
rsu_lib/scenario.py — 시나리오(지도 × 교통 패턴) 이름 → 파일 이름 / 좌표 변환 설정
  Erlangen  : P1, P2, P3          → erlangen.net.xml, erlangen_P2.rou.xml, vehicle_snapshots_2s_P2.csv ...
  Darmstadt : DA_P1, DA_P2, DA_P3 → darmstadt.net.xml, darmstadt_P2.rou.xml, vehicle_snapshots_2s_DA_P2.csv ...
지도마다 net.xml 의 convBoundary 로 시뮬레이션 좌표 변환(x−xmin+25, 위아래 뒤집기)을 맞춘다 (surrogate.set_map).
"""
import os
import re

MAPS = {"": "erlangen", "DA": "darmstadt"}   # 시나리오 접두어 → 지도 이름


def map_of(scen):
    m = re.match(r"^([A-Z]+)_(P\d+)$", scen)
    return (MAPS[m.group(1)], m.group(2)) if m else ("erlangen", scen)


def files(scen):
    mp, pat = map_of(scen)
    rou = "erlangen.rou.xml" if (mp == "erlangen" and pat == "P1") else f"{mp}_{pat}.rou.xml"
    return dict(map=mp, pattern=pat, net=f"{mp}.net.xml", poly=f"{mp}.poly.xml", rou=rou,
                cfg=f"{mp}_{pat}.sumo.cfg", launchd=f"{mp}_{pat}.launchd.xml",
                snap=f"vehicle_snapshots_2s_{scen}.csv",
                grid=("bruteforce_grid_150n_corrected.csv" if mp == "erlangen" else None))


def use(scen):
    """이 시나리오의 지도로 좌표 변환을 맞추고 파일 이름 dict 반환"""
    from rsu_lib import surrogate
    f = files(scen)
    surrogate.set_map(f["net"])
    return f


def boundary(net_xml):
    with open(net_xml, encoding="utf-8") as fh:
        for line in fh:
            m = re.search(r'convBoundary="([^"]+)"', line)
            if m:
                return [float(v) for v in m.group(1).split(",")]
    raise ValueError(f"{net_xml}: convBoundary 없음")


def size(net_xml, margin=25.0):
    x0, y0, x1, y1 = boundary(net_xml)
    return x1 - x0 + 2 * margin, y1 - y0 + 2 * margin
