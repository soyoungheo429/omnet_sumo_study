# Digital Twin-based RSU Placement Optimization for OTA Update Efficiency

본 프로젝트는 **디지털 트윈(Digital Twin)** 환경을 구축하여 차량 소프트웨어 **OTA(Over-the-Air) 업데이트 효율을 극대화**하기 위한 **RSU(Roadside Unit) 배치 최적화** 연구를 수행합니다. 실제 도로망(SUMO)과 무선 네트워크(OMNeT++/Veins) 시뮬레이션을 결합하여, 제한된 예산 하에서 **업데이트 성공 차량 수를 최대화**하는 최적 지점을 도출합니다.

---

## 1. 연구 배경 및 목적
- **배경:** SDV(Software Defined Vehicle) 시대로의 전환에 따라 주행 중 대용량 펌웨어 업데이트의 중요성 증대.
- **문제점:** RSU 설치 비용 제약으로 인해 전역 탐색(Grid Search) 시 시간 복잡도($O(N \times M)$) 폭발 발생.
- **목표:** 1. 실제 도로 네트워크 데이터를 활용한 **지도 기반 후보지 축소(Spatial Filtering)** 기법 제안.
  2. **Brute-Force(전수 조사)**와 **Meta-Heuristics(SA, Greedy)** 알고리즘의 성능 및 연산 시간 비교 분석.
  3. OTA 완료 차량 수를 최대화하는 최적의 RSU 배치 안 도출.

---

## 2. 제안 기법 (Proposed Methodology)

### A. RSU 후보지 생성 및 지도 기반 축소 ($C \rightarrow C_{80}$)
단순 격자 방식의 비효율성을 개선하기 위해 도로망의 정적 정보만을 활용하여 후보지를 80개로 선별합니다.
- **기준:** 교차로 유형(Traffic Light), 진입 차로 수(incLanes), 도로 우선순위(Priority), 교차로 차수(Degree).
- **공간 분산:** 후보지 간 최소 거리($d_{min} = 200m$) 제약을 두어 특정 지역 쏠림 현상 방지.

### B. OTA 서비스 및 네트워크 모델
- **전송 방식:** Unicast 기반 패킷($K$개) 전송 (Selective Repeat ARQ 구조).
- **연속성 보장:** 통신 범위 이탈 후 재진입 시 미수신 패킷부터 이어서 다운로드 가능 (**Resume Capability**).
- **성공 정의:** 시뮬레이션 시간 내에 파일 전체($F$)를 수신한 차량만 '성공'으로 간주.

### C. 최적화 알고리즘 비교 전략
| 비교 항목 | 방식 A: 전역 격자 탐색 (Baseline) | 방식 B: 제안 기법 (Proposed) |
| :--- | :--- | :--- |
| **탐색 범위** | Target Area 전체 $N \times M$ 격자 | 실제 도로 네트워크의 **교차지점(Intersection)** |
| **알고리즘** | Brute-Force (전수 조사) | **Greedy, Simulated Annealing (SA)** |
| **시간 복잡도** | 매우 높음 ($O(N \times M)$) | 낮음 ($O(|C_{80}|)$) |
| **정확도** | 이론적 전역 최적해 도출 | 전역 최적해에 근접한 **부분 최적해** |

---

## 3. 시뮬레이션 환경 (Simulation Setup)
- **Traffic:** SUMO (Berlin-Mitte, Charlottenburg, Reinickendorf 시나리오)
- **Network:** OMNeT++ 6.0 / Veins 5.2 (IEEE 802.11p)
- **OTA Data:** 10MB ~ 1GB (Hyundai/Tesla 실제 업데이트 사례 기반)
- **Metrics:** - **N_complete:** OTA 완료 차량 수 (핵심 지표)
  - **Completion Ratio:** 전체 차량 대비 성공률
  - **Optimality Gap:** BF 대비 알고리즘의 성능 오차 (%)
  - **Execution Time:** 알고리즘별 최적 위치 탐색 소요 시간

---

## 4. 주요 파일 구조
- `/src/veins/modules/application/traci/`: 다중 서비스 에러 수정 및 OTA 로직 C++ 소스
- `/examples/veins/`: 시뮬레이션 설정 파일 (`omnetpp.ini`, `*.net.xml`)
- `/analysis/`: 
  - `candidate_gen.py`: 도로망 기반 후보지 추출 스크립트 ($C \rightarrow C_{80}$)
  - `optimizer.py`: BF, Greedy, SA 알고리즘 구현체
  - `result_plot.py`: 성능 지표 시각화 및 비교 그래프 생성

---


## 5. 기대 효과
- **연산 효율성:** 지도 기반 후보지 축소를 통해 전역 탐색 대비 계산 복잡도 대폭 개선.
- **실무 적용성:** 단순 신호 세기가 아닌, 실제 데이터 다운로드 완료 여부를 기준으로 인프라 가이드라인 제시.
- **확장성:** 향후 딥러닝/강화학습을 이용한 동적 배치 연구의 기반 마련.
