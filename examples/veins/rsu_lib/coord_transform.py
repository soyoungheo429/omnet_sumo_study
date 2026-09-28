# -*- coding: utf-8 -*-
"""
rsu_lib/coord_transform.py
================================================================
이번 세션에서 발견/검증한 좌표 버그의 "정답 공식" 하나만 보관.
다른 모든 알고리즘 스크립트는 이 함수를 import해서만 좌표를 만들어야
한다 (각자 따로 구현하다가 +50/-300 같은 임시방편 버그가 반복됐었음).
================================================================
"""

import re

# net.xml의 <location convBoundary="644465.09,5491786.25,647071.55,5494795.98">
TOPLEFT_X = 644465.09
TOPLEFT_Y = 5491786.25
BOTTOMRIGHT_X = 647071.55
BOTTOMRIGHT_Y = 5494795.98
DIMENSIONS_Y = BOTTOMRIGHT_Y - TOPLEFT_Y  # 3009.73

DEFAULT_MARGIN = 25  # TraCIScenarioManager.ned 기본값


def get_margin_from_ini(ini_path: str) -> float:
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return DEFAULT_MARGIN
    m = re.search(r"\*\.manager\.margin\s*=\s*(\d+)", content)
    return float(m.group(1)) if m else DEFAULT_MARGIN


def traci2omnet(raw_x: float, raw_y: float, margin: float = DEFAULT_MARGIN) -> tuple:
    """Veins의 실제 TraCICoordinateTransformation::traci2omnet()을 그대로 재현.
    raw_x, raw_y: net.xml의 원본 좌표(=UTM 계열, offset 안 뺀 값) 또는
                  UTM으로 변환된 위경도 좌표.
    반환: (Sim_X, Sim_Y) - omnetpp.ini의 *.rsu[i].mobility.x/y 에 그대로 쓸 값."""
    omnet_x = raw_x - TOPLEFT_X + margin
    omnet_y = DIMENSIONS_Y - (raw_y - TOPLEFT_Y) + margin
    return omnet_x, omnet_y


def latlon_to_sim(lat: float, lon: float, margin: float = DEFAULT_MARGIN) -> tuple:
    """위경도 -> UTM -> traci2omnet() 순으로 변환하는 편의 함수."""
    from pyproj import Transformer

    proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    transformer = Transformer.from_crs("epsg:4326", proj_str, always_xy=True)
    utm_x, utm_y = transformer.transform(lon, lat)
    return traci2omnet(utm_x, utm_y, margin)
