# V2X RSU Placement Optimization (SUMO + OMNeT++/Veins)

도로망(SUMO)과 802.11p(WAVE) V2X 무선 네트워크(OMNeT++/Veins) 시뮬레이션을 결합해, 실제 통신 성능(PDR, Packet Delivery Ratio)을 기준으로 **RSU(Roadside Unit) 최적 배치**를 탐색하는 연구입니다. 대상 시나리오는 독일 Erlangen 도로망이며, 차량은 BSM(Basic Safety Message)을 주기적으로 브로드캐스트하고 RSU/차량 간 실제 수신률을 시뮬레이션으로 측정합니다.

---

## 1. 연구 배경 및 목적

- **문제**: RSU 설치 대수와 예산이 제한된 상황에서, "어디에 RSU를 놓아야 통신 성능(PDR)이 가장 좋은가?"
- **접근**: 순수 기하학적 커버리지(반경 안에 몇 대가 들어오는가)가 아니라, **실제 무선 채널의 확률적 특성(페이딩, MAC 백오프, 충돌)까지 반영한 시뮬레이션 기반 PDR**을 최종 평가 지표로 삼음
- **방법**: 후보지 선정 방식이 다른 여러 알고리즘(무작위 격자 탐색, 유전 알고리즘, 시뮬레이티드 어닐링, Greedy Max Coverage 등)을 직접 구현·비교하고, 실측 PDR로 어떤 방식이 실제로 더 나은 배치를 찾는지 검증

## 2. 비교한 알고리즘 (`examples/veins/algo1_*` ~ `algo7_*`)

| # | 접근 방식 | 핵심 스크립트 |
|---|---|---|
| algo1 | 교차로 차수(degree)·밀집도(density) 기반 브루트포스 후보 선정 | `algo1_rsu_bruteforce_candidate.py`, `step1~8_*.py` |
| algo2 | 격자(grid) 기반 브루트포스 탐색 | `algo2_rsu_bruteforce_grid*.py` |
| algo3 | Simulated Annealing (SA) | `algo3_SA_*.py` |
| algo4 | 유전 알고리즘 (GA) | `algo4_GA_*.py` |
| algo5/6 | 다중 RSU(1st/2nd) 배치 평가 | `algo5_multi_*.py`, `algo6_multi_1st2nd.py` |
| algo7 | **Greedy Max Coverage** (차량 스냅샷 기반, submodular 근사 보장) + 실험 파이프라인 전체 | `algo7_rsu_max_coverage.py`, `algo7_evaluate_k_pdr.py`, `algo7_isolated_rsu_pdr.py` 등 |

algo7의 Greedy Max Coverage가 커버리지·PDR 양쪽에서 가장 안정적인 결과를 보여, 이후 모든 정밀 실험(K별 PDR, bitrate 비교, 동기화 실험)의 기준 알고리즘으로 채택했습니다.

## 3. 주요 발견 및 해결한 문제

### ① 좌표 변환 불일치 버그
RSU 배치 좌표를 만들 때(algo7 등) 차량 좌표는 `raw_UTM - OFFSET`만 적용했는데, 실제 차량은 Veins의 `TraCICoordinateTransformation::traci2omnet()`(Y축 뒤집기 + margin=25)을 거쳐 배치됩니다. RSU(`StationaryMobility`)는 이 변환을 거치지 않고 ini에 적힌 좌표를 그대로 쓰기 때문에, **RSU가 실제 교통 흐름과 100m 이상 어긋난 위치에 배치**되고 있었습니다. `algo7_fix_coordinate_transform.py`에서 실제 변환식을 그대로 재현해 후보 좌표를 보정했고, 이후 RSU 단독 PDR이 1%대 → 12%대로 개선되며 이전까지 원인불명이었던 "특정 RSU만 유독 성능이 높은" 현상이 설명됐습니다.

### ② Veins 비콘 동기화 버그 및 실험
`DemoBaseApplLayer.cc`에서 `avoidBeaconSynchronization=false`로 설정하면 비콘이 **아예 발신되지 않는** 버그를 발견해 수정했습니다. 이어서 "RSU들이 비콘을 동시에 보내면 서로 충돌해 PDR이 떨어진다"는 가설을 검증: 랜덤 오프셋(Veins 기본 `avoidBeaconSynchronization=true`)을 켜면 RSU 간 충돌이 14,000회 → 0회로 사라지고 PDR이 10.5% → 17.65%로 개선됨을 실측으로 확인했습니다.

### ③ bitrate에 따른 최적 위치 변화
802.11p bitrate(6Mbps vs 27Mbps)에 따라 유효 통신거리가 크게 달라지며, Greedy Max Coverage가 가정한 고정 반경(150m)과 실제 bitrate별 유효거리가 어긋나 **bitrate가 바뀌면 "최적 RSU 순위"도 바뀐다**는 것을 실측으로 확인했습니다.

## 4. 시뮬레이션 환경

- **Traffic**: SUMO, Erlangen 도로망 (`examples/veins/erlangen.*`)
- **Network**: OMNeT++ / Veins (IEEE 802.11p WAVE), 차량 47대, 시뮬레이션 200s
- **핵심 지표**: PDR(%) = 실제 수신 BSM 수 / (RSU 발신 BSM 수 × 차량 대수) × 100
- **반복 실험**: 시드를 바꿔가며 K회 반복 → 평균/표준편차/에러바 시각화, Shapiro-Wilk/Kruskal-Wallis 등 통계 검정 (`algo7_statistical_analysis.py`)

## 5. 주요 파일 구조

```
src/veins/modules/application/ieee80211p/DemoBaseApplLayer.{cc,ned}   # 비콘 스케줄링 로직 (버그 수정 + indexOffset 실험용 파라미터 추가)
src/veins/modules/mobility/traci/TraCICoordinateTransformation.cc     # 실제 좌표 변환 공식 (traci2omnet)
examples/veins/
  ├── algo1_*, algo2_*, algo3_*, algo4_*, algo5_*, algo6_*            # 비교 대상 배치 알고리즘들
  ├── algo7_rsu_max_coverage.py                                       # Greedy Max Coverage (채택된 알고리즘)
  ├── algo7_fix_coordinate_transform.py                               # 좌표 버그 보정 스크립트
  ├── algo7_evaluate_k_pdr.py                                         # K(RSU 대수)별 PDR 반복 평가 파이프라인
  ├── algo7_isolated_rsu_pdr.py                                       # 후보지 단독(K=1) PDR 비교
  ├── algo7_statistical_analysis.py                                   # 통계 검정
  ├── algo7_backoff_collision_correlation.py                          # MAC 백오프/충돌 상관분석
  ├── step1~8_*.py                                                    # algo1(교차로 기반) 후보 추출~검증 파이프라인
  ├── omnetpp_template.ini                                            # 실행마다 재생성되는 omnetpp.ini의 원본(수정은 항상 여기에)
  └── *.net.xml, *.sumo.cfg                                           # SUMO 도로망/설정
```

## 6. 실행 방법 (예시)

```bash
cd examples/veins

# 1) Greedy Max Coverage로 RSU 후보 27개 선정
python3 algo7_rsu_max_coverage.py --net erlangen.net.xml --csv vehicle_snapshots.csv --k 27

# 2) 좌표 버그 보정
python3 algo7_fix_coordinate_transform.py --input-csv final_selected_rsus.csv

# 3) K(RSU 대수)별 PDR 반복 평가
python3 algo7_evaluate_k_pdr.py --candidates-csv final_selected_rsus_corrected.csv --k-min 1 --k-max 27 --repeats 10

# 4) 후보지 단독(K=1) PDR 비교
python3 algo7_isolated_rsu_pdr.py --candidates-csv final_selected_rsus_corrected.csv --repeats 10
```

실행 결과(반복별 원본 CSV, 요약 CSV, 그래프 PNG)는 `examples/veins/` 아래에 저장되며, 결과 CSV에는 실행 당시 `Bitrate`/`AvoidBeaconSync` 설정이 함께 기록됩니다.

---

본 저장소는 OMNeT++/Veins 프레임워크(GPLv2, `COPYING` 참고) 위에서 개발되었습니다.
