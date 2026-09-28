# RSU 배치 알고리즘 수도코드 (최신/좌표보정 버전 기준)

공통 사항: 모든 알고리즘은 최종적으로 `traci2omnet(x, y, margin)` 함수로 좌표를 보정한다.
```
function traci2omnet(raw_x, raw_y, margin=25):
    sim_x = raw_x - TOPLEFT_X + margin
    sim_y = DIMENSIONS_Y - (raw_y - TOPLEFT_Y) + margin
    return (sim_x, sim_y)
```

---

## algo1: 교차로 차수/밀집도 기반 (Intersection Degree/Density)

**입력**: net.xml, min_dist(=150m), min_degree(=3)
**출력**: 보정된 RSU 후보 좌표 리스트

```
function select_candidates_algo1(net_xml, min_dist, min_degree):
    candidates = []
    for junction in net_xml.junctions:
        if junction.type not in {priority, traffic_light, right_before_left}:
            continue
        degree = len(junction.incoming_lanes)
        if degree >= min_degree:
            candidates.append({id, pos=(x,y), degree})

    for c in candidates:
        c.density = count(o in candidates : o != c and distance(c.pos, o.pos) < min_dist)

    sort candidates by (degree, density) descending

    selected = []
    for c in candidates (정렬된 순서로):
        if no s in selected with distance(c.pos, s.pos) < min_dist:
            selected.append(c)

    return [ traci2omnet(c.pos.x, c.pos.y) for c in selected ]
```

**특징**: 차량 데이터 없이 도로 구조만으로 후보 선정. 최소거리 필터로 밀집 방지.

---

## algo2: 브루트포스 격자 탐색 (Bruteforce Grid Search)

**입력**: grid_size(=150m)
**출력**: 격자 전체 후보 좌표 + 각각의 실측 PDR (전수 조사)

```
function select_candidates_algo2(grid_size):
    candidates = []
    num_x = WIDTH // grid_size
    num_y = HEIGHT // grid_size
    for i in [0, num_x):
        for j in [0, num_y):
            rel_x = i*grid_size + grid_size/2
            rel_y = j*grid_size + grid_size/2
            candidates.append(traci2omnet(rel_x + TOPLEFT_X, rel_y + TOPLEFT_Y))
    return candidates

function run_algo2(grid_size):
    candidates = select_candidates_algo2(grid_size)
    results = []
    for c in candidates:
        pdr = simulate_and_measure_pdr(c)   # RSU 1대만 배치
        results.append((c, pdr))
    best = argmax(results, key=pdr)
    return best, results
```

**특징**: "정답(ground truth)"에 가장 가까움. 단, 격자 해상도(150m)보다 촘촘한 명당은 놓칠 수 있음(실측으로 확인됨).

---

## algo3: Simulated Annealing (SA)

두 버전 사용 — **standard**(단순 SA)와 **smart2**(논문 파라미터 기반 Multi-Start Adaptive SA).

### algo3-standard

```
function run_algo3_standard():
    curr = random_point_in_map()
    curr.pdr = simulate_and_measure_pdr(traci2omnet(curr))
    best = curr
    temp = T_START  # 10.0

    while temp > T_END:  # 0.1
        repeat MAX_ITER times:  # 3
            next = curr + random_offset(-STEP_SIZE, STEP_SIZE)  # STEP_SIZE=150
            next = clip_to_map_bounds(next)
            next.pdr = simulate_and_measure_pdr(traci2omnet(next))

            delta = next.pdr - curr.pdr
            accept = (delta > 0) or (random() < exp(delta / temp))
            if accept:
                curr = next
                if curr.pdr > best.pdr: best = curr
        temp *= ALPHA  # 0.85

    return best
```

### algo3-smart2 (Multi-Start Adaptive SA, 논문 파라미터)

```
function calculate_initial_temperature(sample_size=10):
    pdrs = [simulate_and_measure_pdr(traci2omnet(random_point())) for _ in range(sample_size)]
    valid = [p for p in pdrs if p > 0.1]
    median_pdr = median(valid) if valid else 10.0
    T0 = max(median_pdr / ln(2), 10.0)      # 논문 공식
    Tn = T0 * 1e-4
    return T0, Tn

function run_single_agent(start, T0, Tn):
    curr = start; curr.pdr = simulate_and_measure_pdr(traci2omnet(curr))
    best = curr; temp = T0

    while temp > Tn:
        step_limit = MIN_SIGMA + (MAX_SIGMA - MIN_SIGMA) * (temp - Tn) / (T0 - Tn)  # 적응형 보폭
        repeat MAX_ITER times:  # 10
            angle = random(0, 2π); dist = random(0, step_limit)
            next = clip_to_map_bounds(curr + (cos(angle)*dist, sin(angle)*dist))
            next.pdr = simulate_and_measure_pdr(traci2omnet(next))
            delta = next.pdr - curr.pdr
            accept = (delta > 0) or (random() < exp(delta/temp))
            if accept:
                curr = next
                if curr.pdr > best.pdr: best = curr
        temp *= ALPHA  # 0.3981 (논문값)

    return best

function run_algo3_smart2(num_starts=5):
    T0, Tn = calculate_initial_temperature()
    global_best = None
    for i in range(num_starts):
        start = random_point_in_map()
        result = run_single_agent(start, T0, Tn)
        if global_best is None or result.pdr > global_best.pdr:
            global_best = result
    return global_best
```

**특징**: standard는 단일 탐색가·고정 파라미터, smart2는 실측 PDR 분포로 온도를 자동 계산(논문 공식) + 5개 탐색가 병렬 + 온도별 반복 10회(더 꼼꼼함).

---

## algo4: 유전 알고리즘 (Hybrid GA)

**입력**: POP_SIZE(=10), MAX_GENERATIONS(=10), ELITISM_COUNT(=1)

```
function tournament_selection(population):
    competitors = random_sample(population, 3)
    return max(competitors, key=pdr)

function crossover_and_mutate(p1, p2, gen):
    w1 = p1.pdr / (p1.pdr + p2.pdr);  w2 = 1 - w1     # PDR 가중 중심점
    m = (p1.pos*w1 + p2.pos*w2)
    sigma = MAX_SIGMA - (MAX_SIGMA - MIN_SIGMA) * (gen / MAX_GENERATIONS)  # 적응형
    child = gaussian(mean=m, std=sigma)                # 가우시안 돌연변이
    return clip_to_map_bounds(child)

function run_algo4_hybrid():
    population = [random_point_in_map() for _ in range(POP_SIZE)]
    global_best = None

    for gen in range(1, MAX_GENERATIONS+1):
        for ind in population:
            if ind.pdr <= 0:
                ind.pdr = simulate_and_measure_pdr(traci2omnet(ind))
            if global_best is None or ind.pdr > global_best.pdr:
                global_best = ind

        sort population by pdr descending
        if gen == MAX_GENERATIONS: break

        next_gen = population[:ELITISM_COUNT]           # 엘리트 보존
        while len(next_gen) < POP_SIZE:
            p1 = tournament_selection(population)
            p2 = tournament_selection(population)
            child = crossover_and_mutate(p1, p2, gen)
            next_gen.append(child)
        population = next_gen

    return global_best
```

**특징**: 토너먼트 선택(무작위 3명 중 1등) + PDR 가중 교차 + 적응형 가우시안 돌연변이(초반 넓게 150m → 후반 좁게 5m) + 엘리트 보존.

---

## algo5: 다중 RSU 배치 검증 (Multi-RSU Confirm)

**입력**: 단일 RSU 최적 알고리즘(algo4 등)이 찾은 K=1 명당 좌표

```
function run_algo5_confirm(best_coords_from_algo4, n=2):
    rsu_coords = best_coords_from_algo4[:n]   # 상위 n개(보통 2개) 근접 좌표
    for i, coord in enumerate(rsu_coords):
        place_rsu(i, traci2omnet(coord))
    pdr = simulate_and_measure_pdr_multi(n_rsus=n)
    return pdr
```

**특징**: 새로운 "선정 알고리즘"이 아니라, 이미 찾은 K=1 명당 근처에 RSU를 2대 배치했을 때 실제로 PDR이 오르는지 확인하는 **검증용** 스크립트. (algo6은 algo5와 완전히 동일한 코드였음 — 중복 확인 후 algo5로 통합)

---

## algo7: Greedy Max Coverage

**입력**: 차량 스냅샷 points, 후보 candidates, radius(=150m), K

```
function greedy_max_coverage(points, candidates, radius, K):
    coverage[i] = { p in points : distance(candidates[i], p) < radius }  # 각 후보의 커버 집합
    covered = {}
    selected = []

    repeat K times:
        best_i = argmax_i( |coverage[i] - covered| )   # 아직 안 덮인 포인트를 가장 많이 새로 덮는 후보
        if gain(best_i) <= 0: break
        selected.append(best_i)
        covered = covered ∪ coverage[best_i]

    return [ traci2omnet(candidates[i]) for i in selected ]
```

**특징**: Submodular 함수라 그리디 선택이 최적해 대비 (1-1/e)≈63% 근사 보장. 차량 밀도가 높은 곳 위주로 K개를 "한 번에" 순차 선택 (SA/GA처럼 반복 탐색 아님).

---

## 알고리즘 성격 요약

| 알고리즘 | 유형 | K개 동시 탐색? | 차량 데이터 사용? |
|---|---|---|---|
| algo1 | 규칙 기반 (그래프 구조) | 가능 (상위 K개 반환) | ❌ |
| algo2 | 전수 조사 (Brute-force) | K=1만 | ❌ (PDR 직접 측정) |
| algo3 | 메타휴리스틱 (SA) | K=1만 (현재 구현) | ❌ (PDR 직접 측정) |
| algo4 | 메타휴리스틱 (GA) | K=1만 (현재 구현) | ❌ (PDR 직접 측정) |
| algo5 | 검증용 | K=2 검증만 | - |
| algo7 | 근사 알고리즘 (Greedy) | 가능 (K개 한 번에) | ✅ (커버리지 계산) |
