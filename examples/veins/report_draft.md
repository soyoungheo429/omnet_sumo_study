# RSU 배치 최적화 — 리팩토링 & 알고리즘 재실행 정리

---

## 1. 프로젝트 리팩토링

```
examples/veins/
├── run_all.py                    # 최상위 실행 스크립트
├── rsu_lib/                       # 공통 인프라
│   ├── coord_transform.py         #   좌표 보정 공식
│   ├── sim_runner.py              #   시뮬 실행/PDR 파싱
│   ├── naming.py                  #   파일명 생성
│   ├── run_logger.py              #   풍부한 로그
│   └── config_version.py          #   설정 버전 관리
├── algorithms/                    # 알고리즘별 선정 로직
│   ├── algo1_intersection/        #   교차로 기반
│   ├── algo2_bruteforce_grid/     #   격자 전수조사
│   ├── algo3_simulated_annealing/ #   SA 핵심로직
│   ├── algo4_genetic_algorithm/   #   GA 핵심로직
│   ├── algo5_multi_confirm/       #   다중 검증
│   └── algo7_greedy_coverage/     #   Greedy Coverage
├── configs/versions/              # bitrate/sync 조합 스냅샷
├── experiment_results/            # 결과 저장소
│   ├── single/{algo}/             #   단독(K=1) 결과
│   └── multi/{algo}/              #   다중(K>1) 결과
├── logs/                          # 기타 로그
└── archive/                       # 예전 산출물 격리
    ├── raw_data_old/              #   구버전 결과 132개
    └── deprecated_scripts/        #   중복/구버전 스크립트 22개
```

**전체 실행 방법** (algo1/2/7 통합 완료분):
```bash
cd examples/veins
python3 run_all.py   # CONFIG_MATRIX에 정의된 조합을 순회 실행, experiment_results/에 자동 정리
```
algo3/4/5는 아직 `run_all.py` 미통합 — 아래처럼 개별 실행 후 `experiment_results/`로 수동 이동.

---

## 2. 알고리즘 재실행

### algo3. Simulated Annealing (SA)

**수도코드**
```
temp = T_START
curr = random_point(); curr.pdr = simulate(curr)
while temp > T_END:
    repeat MAX_ITER times:
        next = curr + random_offset(step_size)
        next.pdr = simulate(next)
        accept if next.pdr > curr.pdr, else accept with prob exp(delta/temp)
        if accepted and next.pdr > best.pdr: best = next
    temp *= ALPHA
```
(smart2 버전은 초기온도를 실측 PDR 중앙값으로 자동 계산 — 논문 공식 `T0 = median(PDR)/ln(2)`)

**실행 (리팩토링 후 기준)**
```bash
cd ~/veins/examples/veins
nohup python3 -u algo3_SA_corrected.py > run_log_algo3_corrected.txt 2>&1 &
# 끝나면:
mkdir -p experiment_results/single/algo3/algo3_SA_standard_corrected
mv algo3_sa_results_corrected.csv algo3_sa_convergence_corrected.png run_log_algo3_corrected.txt \
   experiment_results/single/algo3/algo3_SA_standard_corrected/

# smart2(논문 파라미터) 버전:
nohup python3 -u algo3_SA_smart2_corrected.py > run_log_algo3_smart2_corrected.txt 2>&1 &
```

**결과**
- standard: **최고 PDR 30.99%** @ (1093.37, 1397.55)
- smart2: ⏳ 진행 중 (미완료)

**결과 분석**
- algo1(31.28%), algo2 브루트포스(27.64%)와 대등한 수준 → SA도 명당을 잘 찾음
- (smart2 완료 후 standard 대비 개선 여부 추가 예정)

---

### algo4. Genetic Algorithm (GA)

**수도코드**
```
population = [random_point() for _ in range(POP_SIZE)]
for gen in 1..MAX_GENERATIONS:
    evaluate all (simulate)
    sort by pdr; keep elite
    while next_gen not full:
        p1, p2 = tournament_selection(population)  # 무작위 3명 중 1등
        sigma = adaptive(gen)                        # 초반 넓게 → 후반 좁게
        child = gaussian_mutate(weighted_mean(p1,p2), sigma)
        next_gen.append(child)
    population = next_gen
```

**실행 (리팩토링 후 기준)**
```bash
cd ~/veins/examples/veins
nohup python3 -u algo4_GA_hybrid_corrected.py > run_log_algo4_hybrid_corrected.txt 2>&1 &
# 끝나면:
mkdir -p experiment_results/single/algo4/algo4_GA_hybrid_corrected
mv ga_hybrid_final_results_corrected.csv ga_hybrid_convergence_corrected.png run_log_algo4_hybrid_corrected.txt \
   experiment_results/single/algo4/algo4_GA_hybrid_corrected/
```

**결과**: ⏳ 대기 중 (미실행)

**결과 분석**: (실행 후 추가 예정)

---

### algo5. 다중 RSU 배치 검증 (K=2 전수조사)

**수도코드**
```
top_N = load_top_candidates(N=27, by=single_pdr)  # algo1의 보정된 27개 + 단독 PDR
for (rsu1, rsu2) in combinations(top_N, 2):        # 27C2 = 351개
    combined_pdr = simulate_multi([rsu1, rsu2])
best_pair = argmax(combined_pdr)
```

**실행 (리팩토링 후 기준)**
```bash
cd ~/veins/examples/veins
nohup python3 -u algo5_multi_baseline_corrected.py > run_log_algo5_baseline_corrected.txt 2>&1 &
# 끝나면:
mkdir -p experiment_results/multi/algo5/algo5_baseline_351combo
mv algo5_baseline_top27_c2_results_corrected.csv run_log_algo5_baseline_corrected.txt \
   experiment_results/multi/algo5/algo5_baseline_351combo/
```

**결과**: ⏳ 대기 중 (미실행)

**결과 분석**: (실행 후 추가 예정 — algo1 다중 K=2 결과인 "Rank1+Rank2"와 비교해서, 순위 기반 조합이 진짜 최선인지 검증할 예정)

---

## 3. 전체 비교

| 알고리즘 | 방식 | 최고 PDR (K=1) | 비고 |
|---|---|---|---|
| algo1 (교차로) | 규칙 기반 | 31.28% | |
| algo2 (격자) | 전수조사 | 27.64% | 150m 해상도 한계 있음 |
| algo3 (SA-standard) | 메타휴리스틱 | 30.99% | |
| algo3 (SA-smart2) | 메타휴리스틱(논문) | ⏳ | |
| algo4 (GA-hybrid) | 메타휴리스틱 | ⏳ | |
| algo7 (Greedy Coverage) | 근사 알고리즘 | (K별 상이) | K=1~27 전체 스윕 완료 |

*(전체 비교표는 algo3 smart2 / algo4 / algo5 완료 후 최종 업데이트)*

---

## 4. 남은 할 일

1. algo3 smart2, algo4 hybrid GA, algo5(351조합) 실행 완료 대기 → `experiment_results/`로 이동
2. algo1 다중 RSU(K=1~27) 스윕 완료
3. 위 결과들로 "전체 비교" 표 최종 완성 + 분석 서술
4. algo3/4를 `run_all.py`/`rsu_lib`로 완전 통합 (현재는 독립 스크립트로만 실행됨 — 기술 부채)
5. algo2 격자 탐색 결과와 algo1/algo7 최고점 비교해 "격자 해상도 한계" 정량화
6. (선택) algo5를 27개 전체가 아니라 40개+로 확장해 원본 규모(780조합)와 비교
