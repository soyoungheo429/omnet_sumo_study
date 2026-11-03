# 강화학습(RL) 기반 RSU·시설 배치 문헌 정리 (2026-11-03)

## 우리가 구현한 것과 근거
| 우리 구현 | 근거 논문 | 공통점 |
|---|---|---|
| PPO (순차 배치, 고른 곳 마스킹, 액터-크리틱) | Greta (Wu et al., IEEE TMC 2024) — RSU 배치를 직접 다룬 RL 논문 | 상태=배치 현황, 행동=다음 RSU 위치, 마스킹, PPO |
| DQN (Q(s,a) 후보별 공유 신경망, 경험재생·타깃망) | GCOMB (Manchanda et al., NeurIPS 2020, max coverage), Qiu et al. (ICC 2020, 기지국 배치, DDQN) | 보상=한계 커버리지 이득 |
| (비교 기준) Greedy / 최적해(ILP) | Nemhauser 1978: greedy (1−1/e) 보장 | GCOMB도 품질은 greedy와 거의 같고 속도만 빠름 |

## 논문 목록 (검색으로 실재 확인)
1. Greta: Towards a General Roadside Unit Deployment Framework — Wu, X. 외, IEEE TMC 23(7), 2024. https://doi.org/10.1109/TMC.2023.3335853
   - PPO, 84×84 격자 상태, 행동=다음 RSU 격자(마스킹), 보상=road/traffic coverage−overlap. SA 대비 coverage +2~7%. greedy 대비 수치는 없음.
2. LAMP: Learning Automata-Based Multi-Objective Optimization for RSU Placement in IoV — Kumari, J. 외, IEEE OJVT 7, 2026. https://doi.org/10.1109/OJVT.2026.3692780 (초록만 확인)
3. Reinforcement Learning-based Dynamic Service Placement in Vehicular Networks — Talpur & Gurusamy, VTC2021-Spring. https://arxiv.org/abs/2105.15022
4. DRLD-SP: Deep RL-based Dynamic Service Placement in Edge-Enabled IoV — Talpur & Gurusamy, IEEE IoT-J. https://arxiv.org/abs/2106.06291
5. Leveraging UAVs for Coverage in Cell-Free Vehicular Networks: A DRL Approach — Samir, M. 외, IEEE TMC 20(9), 2021. https://doi.org/10.1109/TMC.2020.2991326
6. Placement Optimization of Aerial Base Stations with Deep Reinforcement Learning — Qiu, J. 외, IEEE ICC 2020. https://arxiv.org/abs/1911.08111
7. GCOMB: Learning Budget-constrained Combinatorial Algorithms over Billion-sized Graphs — Manchanda, S. 외, NeurIPS 2020. https://arxiv.org/abs/1903.03332
8. Attention, Learn to Solve Routing Problems! — Kool, W. 외, ICLR 2019. https://arxiv.org/abs/1803.08475
9. DeepMCLP: Solving the MCLP with Deep RL for Urban Spatial Computing — Wang, S. 외, 2023. https://doi.org/10.25436/E2KK5V
10. Swap-based Deep RL for Facility Location Problems in Networks — Guo, W. 외, arXiv 2023. https://arxiv.org/abs/2312.15658
11. A Multi-Agent DRL Method ... Continuous Location of Express Delivery Stations — Lyu, Y. 외, IJGI 14(12):461, 2025. https://doi.org/10.3390/ijgi14120461
12. (RL 아님, GA 비교용) 궤적 기반 2단계 RSU 배치 + 개선 GA, SUMO+OMNeT++/Veins 검증 — Zhang, S. 외, IEEE T-ITS 26(2). https://ir.bjut.edu.cn/item/414119

## 정리
- 정적(고정 교통) 커버리지 최대화는 submodular → greedy가 이론·실험 모두 강함. RL은 대부분 greedy와 비슷(GCOMB).
- RL이 의미 있는 곳: (1) 시간대별 교통 변화에 따른 재배치/활성화, (2) 다른 맵·교통으로 일반화(학습 후 즉시 추론), (3) 공평도·간섭처럼 submodular가 아닌 목적, (4) 비싼 시뮬레이터 대신 근사 모델로 학습.
