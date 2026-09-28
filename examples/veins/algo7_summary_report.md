# RSU 배치 최적화 실험 최종 요약 보고서

**대상 시나리오**: Erlangen 도로망, SUMO/OMNeT++/Veins, 802.11p(WAVE) V2X 시뮬레이션
**차량 대수**: 47대 (시나리오 실측 기준) · **시뮬레이션 시간**: 200s
**RSU 후보**: Greedy Max Coverage로 선정된 27개 교차로 (`final_selected_rsus.csv`)

---

## 1. 변경한 파라미터와 근거

| 파라미터 | 파일 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|---|
| `*.manager.updateInterval` | `omnetpp_template.ini` | 1s | **0.05s** | RSU/차량 BSM 송신 주기가 0.1s(10Hz)이므로, Nyquist 샘플링 정리에 따라 에일리어싱 없이 위치를 재구성하려면 최소 2배인 20Hz(0.05s)로 TraCI 동기화 주기를 맞춰야 함 |
| SUMO `step-length` | `erlangen.sumo.cfg` | 0.1s | **0.05s** | `manager.updateInterval=0.05s`가 실제로 새 위치를 받으려면 SUMO 자체도 0.05s 단위로 전진해야 함 (step-length가 더 크면 TraCI가 물어봐도 절반은 직전과 동일한 좌표를 받게 됨) |
| `*.**.nic.mac1609_4.bitrate` | 위와 동일 | 6Mbps | **27Mbps** (802.11p 최댓값) | BSM 페이로드가 작아 변조오류 증가 폭이 제한적일 것으로 예상했고, bitrate가 높을수록 전송시간이 짧아져 RSU 간 시간축 충돌 확률이 줄어들 것으로 기대함 |

⚠️ **2단계 근거는 실험 결과 반박됨**: 27Mbps(고차 변조)는 6Mbps보다 훨씬 높은 SINR이 필요해서, 이 배치의 tx power/noise floor 조건에서는 오히려 PDR이 크게 낮아졌다 (아래 3절 참고). 다만 **K 간 상대 비교는 여전히 유효**하다고 보고 27Mbps를 유지한 채 진행함.

---

## 2. 실험 과정에서 발견/수정한 이슈

실험 도중 아래 4가지 문제를 순서대로 발견하고 수정했다. 특히 ②, ③은 초기 실험 결과(K별 PDR이 시드와 무관하게 완전히 동일)를 무효화시켰던 핵심 원인이었다.

| # | 문제 | 증상 | 조치 |
|---|---|---|---|
| ① | `algo7_rsu_max_coverage.py`가 `--net`(교차로 자동추출)으로 후보를 불러올 때, 차량 좌표는 UTM 오프셋을 빼서 로컬 좌표로 변환하는데 **후보지 좌표는 변환을 안 함** | k=27 요청 시 1스텝만에 "커버 가능한 차량 0대"로 조기 종료 | 후보지 로딩 직후 동일한 오프셋 적용 (코드 수정) |
| ② | `omnetpp.ini`는 `algo7_evaluate_k_pdr.py` 실행마다 `omnetpp_template.ini`에서 **자동 재생성**되는데, `updateInterval`/`bitrate` 수정을 `omnetpp.ini`에만 직접 해서 재실행 시 계속 원복됨 | 여러 차례 실험이 실제로는 옛날 설정(1s/6Mbps)으로 돌아간 것으로 뒤늦게 확인 | `omnetpp_template.ini`(진짜 소스)에 반영 |
| ③ | `config.xml`의 두 AnalogueModel이 `thresholding="true"`로 설정된 상태 + ②의 문제가 겹쳐, K별 반복실험에서 **시드를 바꿔도 PDR이 완전히 동일**하게 나옴 | 다중 시드 반복실험 자체가 무의미했음 | ②를 먼저 바로잡은 뒤 `thresholding="false"`로 변경 → 실제 확률적 변동 확인됨 |
| ④ | `PhyLayer80211p.ned`의 `collectCollisionStatistics` 기본값이 `false`라, PHY 계층 충돌(interference로 인한 실패) 통계가 전혀 기록되지 않고 있었음 | `.sca`에 `ncollisions` 스칼라 자체가 안 찍힘 | `*.**.nic.phy80211p.collectCollisionStatistics = true` 추가 |

---

## 3. 3단계: 다중 시드 반복실험 (K=1~27 × 30회, 총 810회)

- 스크립트: `algo7_evaluate_k_pdr.py` (Rank 기준 상위 K개 누적 배치)
- 총 소요시간: **150.4분** (1회 평균 11.1초, K가 커질수록 소요시간도 증가: K=1은 약 5~7초, K=27은 15~59초)

| K | 평균 PDR(%) | K | 평균 PDR(%) | K | 평균 PDR(%) |
|---|---|---|---|---|---|
| 1 | 1.08 | 10 | 1.11 | 19 | 0.70 |
| 2 | 0.54 | 11 | 1.01 | 20 | 0.71 |
| 3 | 0.36 | 12 | 0.92 | 21 | 0.69 |
| 4 | 0.45 | 13 | 0.94 | 22 | 0.65 |
| 5 | 0.36 | 14 | 0.96 | 23 | 0.63 |
| 6 | 0.30 | **15** | 0.89 | 24 | 0.60 |
| 7 | 0.26 | 16 | 0.84 | 25 | 0.58 |
| **8** | **1.29** | 17 | 0.79 | 26 | 0.56 |
| 9 | 1.23 | 18 | 0.75 | 27 | 0.54 |

**핵심 패턴**: K=1→7 완만히 감소 → **K=8에서 급등(0.26%→1.29%, 약 5배)** → K=9~27 다시 완만히 감소.

전체 그래프: `algo7_k_vs_pdr_errorbar.png`, 원본 데이터: `algo7_k_vs_pdr_multirun_raw.csv`

---

## 4. 4단계: 통계 검정

| 검정 | 결과 |
|---|---|
| 정규성 (Shapiro-Wilk, α=0.05) | **27/27개 K 그룹 전부 정규성 기각** |
| 전체 비교 | **Kruskal-Wallis**: H=806.90, **p=2.44×10⁻¹⁵³** (극도로 유의함) |
| 사후검정 | Bonferroni 보정 pairwise Mann-Whitney U: 351쌍 중 **349쌍 유의** (거의 모든 K값 쌍이 서로 통계적으로 다름) |

**결론**: RSU 배치 대수(K)에 따라 PDR이 통계적으로 매우 유의하게 달라진다. K=8의 급등도 이 검정으로 뒷받침된다.

산출물: `algo7_stats_normality.csv`, `algo7_stats_summary_ci.csv`(평균±95%CI), `algo7_stats_posthoc.csv`, `algo7_stats_mean_ci_barplot.png`

---

## 5. 5단계: Backoff/Collision 상관분석

대표 K값(1, 5, 8, 15, 27) × 10회 재측정 (`algo7_backoff_collision_correlation.py`)

| K | 평균 PDR(%) | TimesIntoBackoff | SlotsBackoff | NCollisions |
|---|---|---|---|---|
| 1 | 1.08 | 2,014 | 3,020 | 0.0 |
| 5 | 0.36 | 10,014 | 14,939 | 0.0 |
| 8 | 1.29 | 16,014 | 24,068 | 0.0 |
| 15 | 0.89 | 30,014 | 44,995 | 25.9 (1회 이상치 제외 시 거의 0) |
| 27 | 0.54 | 54,214 | 81,379 | 0.0 |

- **NCollisions는 K=27까지도 거의 항상 0** → RSU 간 실제 간섭 충돌은 사실상 없음. Greedy Max Coverage가 커버리지 중복을 최소화하도록 후보를 뽑은 결과로 해석됨.
- TimesIntoBackoff/SlotsBackoff는 **RSU 1대당 약 2,014회로 K에 정확히 비례** — 혼잡도가 아니라 단순 전송 시도 총량을 반영.
- PDR과의 상관관계: Pearson은 유의(r=-0.35, p=0.012)하지만 **Spearman은 유의하지 않음(p≈0.16~0.17)** → 견고한 인과관계가 아니라, K=8의 비단조적 패턴에 의한 통계적 왜곡으로 판단됨.

**원래 가설("RSU가 많을수록 충돌이 늘어 PDR이 떨어진다")은 이 배치에서는 관찰되지 않았다.**

---

## 6. K=8 이상치 원인 탐구 (미해결)

RSU 후보를 하나씩 단독(K=1)으로 배치해 비교한 결과(`algo7_isolated_rsu_pdr.py`), **Rank 8(SUMO junction `286769261`, 좌표 1270.2/1451.0, type: priority)**의 단독 PDR이 **8.49%**로 27개 후보 중 압도적 1위였다 (2위 Rank 14는 1.22%, 나머지 18개 후보는 단독 PDR 0%).

네 가지 가설을 세워 순서대로 검증했으나 **모두 기각**되었다:

| 가설 | 검증 방법 | 결과 |
|---|---|---|
| 단순 거리 | 거리 임계값별 커버 포인트 수 vs PDR 상관분석 | 전 구간 상관 없음 (p>0.3) |
| 건물 LOS 차단 | `erlangen.poly.xml` 건물 폴리곤과의 교차 판정 반영 | 여전히 무관 (p>0.7). LOS 100%인 후보끼리도 PDR이 0~1.22%로 상이 |
| 속도/체류시간(정체) | 차량 순간속도 역산 후 상관분석 | 무관 (p=0.75). 오히려 2위 후보(Rank 14)가 가장 빠른 속도 구간 |
| 최소 접근거리 | 후보별 차량과의 최소거리 | Pearson 무관, Spearman은 약한 신호(p=0.03)이나 반례 다수(Rank 22가 더 가까운데 PDR 0%) 존재 |

**결론**: 거리·건물차단·속도·최소거리 등 정적 스냅샷 기반 지표로는 Rank 8의 압도적 성능을 설명하지 못했다. **미식별 요인으로 남기며, 향후 과제로 제안한다** (예: 페이딩/차선별 미세 지오메트리, 특정 시간대 국소 정체 등 스냅샷에 잡히지 않는 동적 요인 가능성).

---

## 7. 시각화 산출물 목록

| 파일 | 내용 |
|---|---|
| `algo7_k_vs_pdr_errorbar.png` | K vs PDR 에러바 (3단계) |
| `algo7_stats_mean_ci_barplot.png` | K별 평균±95%CI 막대그래프 (4단계) |
| `algo7_backoff_collision_scatter.png` | NCollisions vs PDR 산점도 (5단계) |
| `algo7_isolated_rsu_pdr_errorbar.png`, `algo7_isolated_rsu_received_bar.png` | 27개 후보 단독 PDR/수신량 비교 |
| `algo7_effective_radius_correlation.png`, `algo7_effective_radius_los_correlation.png`, `algo7_dwell_speed_best_scatter.png` | Rank 8 원인 탐구 상관분석 |
| `vehicle_scatter_plot.png` | 차량 밀도 히트맵 (로그 스케일) |
| Rank 8 위치 지도 (Artifact) | Erlangen 도로망/건물 위 27개 RSU 후보 + Rank 8 강조 |

---

## 8. 향후 과제

1. **Rank 8 이상치의 진짜 원인 규명** — 고정 거리 프로브 노드를 이용한 통제 실험(방법 B), 또는 차선 단위 미세 지오메트리 분석
2. **bitrate 재검토** — 27Mbps에서 PDR이 절대적으로 매우 낮으므로(K별 0.26~1.29%), 6~24Mbps 구간에서 PDR을 극대화하는 지점을 별도로 탐색
3. **RSU 배치 알고리즘 개선** — 현재 Greedy Max Coverage는 150m 반경 가정 기반인데, 이 반경이 실제 27Mbps 유효거리와 맞지 않는다는 것이 확인됐으므로, 유효거리 재보정 또는 다른 목적함수(예: LOS 가중 커버리지) 도입 검토
