# -*- coding: utf-8 -*-
"""
rsu_lib/placement.py
================================================================
다중 RSU 배치 알고리즘 모음 (평가는 rsu_lib/surrogate.py 의 커버리지 행렬로 빠르게)

  CoverageMatrix          후보지 × 차량스냅샷점 커버 여부(bool) 행렬
  greedy_marginal()       [수정 알고리즘] 매 단계 "새로 덮는 양(한계이득)"이 최대인 후보 추가
                          → K가 늘 때 증가폭이 항상 줄어드는(오목한) 곡선, 엎치락뒤치락 없음
  swap_local_search()     Greedy 해에서 RSU 1개씩 바꿔보며 개선 (1-swap)
  SetGA                   [다중 RSU GA] 개체 = K개 위치의 "집합(그룹)", 부모 그룹 2개 → 자식 그룹
  ReinforcePolicy         [강화학습] 순차 배치 MDP + REINFORCE (greedy rollout baseline)
================================================================
"""
import numpy as np


class CoverageMatrix:
    def __init__(self, surrogate, coords, ids=None, weights=None):
        self.coords = np.asarray(coords, float)
        self.ids = ids if ids is not None else [f"c{i}" for i in range(len(coords))]
        self.M = np.vstack([surrogate.covered(tuple(c)) for c in self.coords])   # (C, N) bool
        self.n_pts = self.M.shape[1]
        self.w = np.ones(self.n_pts) if weights is None else np.asarray(weights, float)
        self.single = (self.M * self.w).sum(1) / self.w.sum() * 100

    def cover(self, idx):
        if len(idx) == 0:
            return 0.0
        return float(self.w[self.M[list(idx)].any(0)].sum() / self.w.sum() * 100)

    def subset_points(self, mask):
        """일부 차량 점만 쓰는 새 행렬(학습/검증 분리용)"""
        o = object.__new__(CoverageMatrix)
        o.coords, o.ids = self.coords, self.ids
        o.M = self.M[:, mask]
        o.n_pts = o.M.shape[1]
        o.w = self.w[mask]
        o.single = (o.M * o.w).sum(1) / o.w.sum() * 100
        return o


# ---------------------------------------------------------------- Greedy
def greedy_marginal(cm, K, start=None):
    """반환: 선택 순서 idx 리스트, 누적 커버(%) 리스트, 한계이득(%) 리스트"""
    sel = list(start or [])
    covered = cm.M[sel].any(0) if sel else np.zeros(cm.n_pts, bool)
    cums, gains = [], []
    tot = cm.w.sum()
    for _ in range(K - len(sel)):
        newc = ((cm.M & ~covered) * cm.w).sum(1) / tot * 100
        newc[sel] = -1
        i = int(np.argmax(newc))
        sel.append(i)
        covered |= cm.M[i]
        gains.append(float(newc[i]))
        cums.append(float(cm.w[covered].sum() / tot * 100))
    return sel, cums, gains


def swap_local_search(cm, sel, max_rounds=20):
    """RSU 하나를 다른 후보로 바꿔서 커버가 늘면 교체, 더 이상 안 늘 때까지 반복"""
    sel = list(sel)
    best = cm.cover(sel)
    for _ in range(max_rounds):
        improved = False
        for pos in range(len(sel)):
            others = [s for j, s in enumerate(sel) if j != pos]
            base = cm.M[others].any(0) if others else np.zeros(cm.n_pts, bool)
            gain = ((cm.M & ~base) * cm.w).sum(1)
            gain[others] = -1
            i = int(np.argmax(gain))
            val = float(cm.w[base | cm.M[i]].sum() / cm.w.sum() * 100)
            if val > best + 1e-9 and i != sel[pos]:
                sel[pos], best, improved = i, val, True
        if not improved:
            break
    return sel, best


# ---------------------------------------------------------------- Set-based GA
class SetGA:
    """
    개체(individual) = K개 후보 인덱스의 집합 = RSU 그룹 {(x1,y1),...,(xK,yK)}
    - 초기화  : 무작위 K개 (seed_sets가 있으면 일부 개체로 넣음)
    - 선택    : 토너먼트(3)
    - 교차    : 부모 두 그룹의 합집합(최대 2K개)에서 "빼도 손해가 가장 작은 RSU"를 하나씩 제거해 K개로 (Alp et al. 2003, p-median GA 방식)
    - 돌연변이: 그룹 안 RSU 1개를 근처(neighbor_r m 이내) 후보 또는 전체 무작위 후보로 교체
    - 엘리트  : 상위 n_elite 그룹은 다음 세대로 그대로
    세대별 모든 그룹(좌표 K개)을 history에 저장 → 시각화/CSV
    """

    def __init__(self, cm, K, pop=40, gens=60, n_elite=4, p_mut=0.4, neighbor_r=200.0,
                 seed=0, seed_sets=None, random_init_only=False):
        self.cm, self.K, self.pop, self.gens = cm, K, pop, gens
        self.n_elite, self.p_mut = n_elite, p_mut
        self.rng = np.random.default_rng(seed)
        self.seed_sets = [] if random_init_only else (seed_sets or [])
        C = cm.coords
        d = np.hypot(C[:, None, 0] - C[None, :, 0], C[:, None, 1] - C[None, :, 1])
        self.neigh = [np.where((d[i] <= neighbor_r) & (d[i] > 0))[0] for i in range(len(C))]
        self.history = []          # (gen, ind, fitness, sorted idx tuple)
        self.n_evals = 0

    def fit(self, ind):
        self.n_evals += 1
        return self.cm.cover(ind)

    def _random_ind(self):
        return list(self.rng.choice(len(self.cm.coords), self.K, replace=False))

    def _crossover(self, a, b):
        pool = list(dict.fromkeys(list(a) + list(b)))
        while len(pool) < self.K:
            pool.append(int(self.rng.integers(len(self.cm.coords))))
            pool = list(dict.fromkeys(pool))
        M, w = self.cm.M, self.cm.w
        while len(pool) > self.K:
            cnt = M[pool].sum(0)
            # 각 RSU를 뺐을 때 잃는 커버 (자기만 덮던 점의 가중치 합)
            loss = [(w[(M[p]) & (cnt == 1)]).sum() for p in pool]
            pool.pop(int(np.argmin(loss)))
        return pool

    def _mutate(self, ind):
        ind = list(ind)
        if self.rng.random() < self.p_mut:
            j = int(self.rng.integers(self.K))
            nb = self.neigh[ind[j]]
            if len(nb) and self.rng.random() < 0.7:
                cand = int(self.rng.choice(nb))
            else:
                cand = int(self.rng.integers(len(self.cm.coords)))
            if cand not in ind:
                ind[j] = cand
        return ind

    def run(self, log_every=0):
        P = [list(s)[: self.K] for s in self.seed_sets][: self.pop]
        while len(P) < self.pop:
            P.append(self._random_ind())
        F = [self.fit(p) for p in P]
        best_curve = []
        for g in range(1, self.gens + 1):
            for i, (p, f) in enumerate(zip(P, F)):
                self.history.append((g, i, f, tuple(sorted(int(x) for x in p))))
            order = np.argsort(F)[::-1]
            best_curve.append(F[order[0]])
            if log_every and g % log_every == 0:
                print(f"    gen {g:3d} best={F[order[0]]:.2f} mean={np.mean(F):.2f}")
            if g == self.gens:
                break
            newP = [P[i] for i in order[: self.n_elite]]
            newF = [F[i] for i in order[: self.n_elite]]
            while len(newP) < self.pop:
                t1 = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])
                t2 = max(self.rng.choice(self.pop, 3, replace=False), key=lambda i: F[i])
                child = self._mutate(self._crossover(P[t1], P[t2]))
                newP.append(child)
                newF.append(self.fit(child))
            P, F = newP, newF
        i = int(np.argmax(F))
        return P[i], F[i], best_curve


# ---------------------------------------------------------------- RL (REINFORCE)
def _features(cm, covered, sel, dist_to_sel):
    tot = cm.w.sum()
    newc = ((cm.M & ~covered) * cm.w).sum(1) / tot * 100       # 한계이득
    single = cm.single
    overlap = np.where(single > 0, 1 - newc / np.maximum(single, 1e-9), 0)
    dn = np.minimum(dist_to_sel, 1500) / 1500.0
    phi = np.stack([newc / 10, single / 10, overlap, dn, np.ones_like(newc)], 1)
    return phi, newc


class ReinforcePolicy:
    """
    순차 배치 MDP
      상태  : 현재 커버된 차량점 집합 + 이미 놓은 RSU
      행동  : 다음 RSU 후보 하나 (이미 놓은 곳은 제외)
      보상  : 새로 덮은 비율(한계이득, %) — 에피소드 합 = 최종 커버
      정책  : 후보별 특징 φ = [한계이득, 단독커버, 겹침비율, 가장 가까운 RSU까지 거리, 1] 의 선형 점수 → softmax
      학습  : REINFORCE, baseline = 같은 상태에서 greedy 정책의 결과(greedy rollout)
    특징이 후보 수와 무관해서 다른 교통 데이터/다른 후보 풀에도 그대로 적용 가능
    """

    def __init__(self, n_feat=5, lr=0.05, temp=1.0, seed=0):
        self.theta = np.zeros(n_feat)
        self.theta[0] = 1.0      # 처음엔 한계이득을 조금 선호하는 정책에서 시작
        self.lr, self.temp = lr, temp
        self.rng = np.random.default_rng(seed)

    def _probs(self, phi, mask):
        z = phi @ self.theta / self.temp
        z[mask] = -np.inf
        z -= z[~mask].max()
        p = np.exp(z)
        return p / p.sum()

    def rollout(self, cm, K, greedy=False):
        C = cm.coords
        covered = np.zeros(cm.n_pts, bool)
        sel, grads, rewards = [], [], []
        dist = np.full(len(C), 1e9)
        for _ in range(K):
            phi, newc = _features(cm, covered, sel, dist)
            mask = np.zeros(len(C), bool)
            mask[sel] = True
            p = self._probs(phi, mask)
            a = int(np.argmax(p)) if greedy else int(self.rng.choice(len(C), p=p))
            grads.append(phi[a] - p @ phi)        # ∇log π(a|s) (선형 softmax)
            rewards.append(newc[a])
            sel.append(a)
            covered |= cm.M[a]
            dist = np.minimum(dist, np.hypot(C[:, 0] - C[a, 0], C[:, 1] - C[a, 1]))
        return sel, float(np.sum(rewards)), grads, rewards

    def train(self, train_cms, K_range, iters=300, batch=16, log_every=50):
        curve = []
        for it in range(1, iters + 1):
            g_total = np.zeros_like(self.theta)
            rets = []
            for _ in range(batch):
                cm = train_cms[int(self.rng.integers(len(train_cms)))]
                K = int(self.rng.choice(K_range))
                base = greedy_marginal(cm, K)[1][-1]
                sel, R, grads, _ = self.rollout(cm, K)
                adv = R - base
                g_total += adv * np.sum(grads, 0)
                rets.append(R - base)
            self.theta += self.lr * g_total / batch
            curve.append(float(np.mean(rets)))
            if log_every and it % log_every == 0:
                print(f"    iter {it:4d}  (RL − greedy) 평균 = {np.mean(curve[-log_every:]):+.3f}%p  θ={np.round(self.theta, 2)}")
        return curve
