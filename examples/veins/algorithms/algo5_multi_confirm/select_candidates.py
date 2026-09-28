# -*- coding: utf-8 -*-
"""
algo5_multi_confirm/select_candidates.py
================================================================
"선정 알고리즘"이 아니라, algo4(GA)가 K=1로 찾은 최적 위치 근처에
RSU 2대를 배치했을 때 PDR이 어떻게 되는지 확인하는 검증용 스크립트.
(원본 algo5_multi_1st2nd.py / algo6_multi_1st2nd.py는 완전히 동일한
코드였음 - 중복이라 이 하나로 통합)

주의: 아래 좌표는 GA가 찾은 값을 그대로 하드코딩한 것이라, 좌표
보정(traci2omnet)이 이미 적용됐는지 원본에서 확인되지 않음 - 재실행 시
반드시 algo4_GA_corrected.py의 최신 출력으로 갱신해서 써야 함.
================================================================
"""

# TODO: algo4_GA_corrected.py 재실행 결과로 갱신 필요 (아래는 예전 값, 좌표보정 이전)
LEGACY_RSU_COORDS = [
    (1306.06, 1348.74),
    (1307.27, 1348.41),
]


def select_candidates(n: int = 2) -> list:
    """반환: [(Sim_X, Sim_Y), ...] - n개까지 반환 (기본 2개)."""
    return LEGACY_RSU_COORDS[:n]
