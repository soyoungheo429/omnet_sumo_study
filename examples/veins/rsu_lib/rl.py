# -*- coding: utf-8 -*-
"""
rsu_lib/rl.py — RSU 순차 배치 강화학습 (numpy만 사용, PyTorch 불필요)
================================================================
MDP (Greta, IEEE TMC 2024 / GCOMB, NeurIPS 2020 과 같은 '순차 구성형' 정식화)
  에피소드 : RSU를 K개 하나씩 놓는 과정 (K는 에피소드마다 1~10 중 무작위)
  상태 s_t : 지금까지 덮인 차량점 + 놓은 RSU + 남은 개수
  행동 a_t : 아직 안 고른 후보지 하나 (고른 곳은 마스킹 = Greta의 action mask)
  보상 r_t : 이번 RSU가 새로 덮은 비율(%) → 에피소드 보상 합 = 최종 커버(서비스 비율 근사)
  후보지별 특징 φ(s,a) (후보 수와 무관 → 다른 교통 데이터/후보 풀에도 적용 가능)
     [한계이득, 단독커버, 겹침비율, 가장 가까운 RSU까지 거리, 진행률 t/K, 남은비율 (K−t)/K]
알고리즘
  PPO : 액터(후보별 공유 MLP → 점수 → softmax) + 크리틱(상태 요약 MLP → 가치), clip ε=0.2   ← Greta
  DQN : Q(s,a)=후보별 공유 MLP, 경험 재생 + 타깃 네트워크, ε-greedy                         ← GCOMB/Qiu
================================================================
"""
import numpy as np

from rsu_lib.placement import greedy_marginal


# ---------------------------------------------------------------- 작은 MLP (수동 역전파)
class MLP:
    def __init__(self, sizes, rng, scale=0.5):
        self.W = [rng.normal(0, scale / np.sqrt(a), (a, b)) for a, b in zip(sizes[:-1], sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]
        self.m = [np.zeros_like(p) for p in self.W + self.b]   # Adam
        self.v = [np.zeros_like(p) for p in self.W + self.b]
        self.t = 0

    def forward(self, x):
        self.cache = [x]
        h = x
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            h = h @ W + b
            if i < len(self.W) - 1:
                h = np.tanh(h)
            self.cache.append(h)
        return h

    def backward(self, gout):
        gW, gb = [None] * len(self.W), [None] * len(self.b)
        g = gout
        for i in reversed(range(len(self.W))):
            h_in = self.cache[i]
            gW[i] = h_in.T @ g
            gb[i] = g.sum(0)
            if i > 0:
                g = (g @ self.W[i].T) * (1 - self.cache[i] ** 2)
        return gW + gb

    def step(self, grads, lr=1e-3, b1=0.9, b2=0.999):
        self.t += 1
        params = self.W + self.b
        for k, (p, g) in enumerate(zip(params, grads)):
            g = np.clip(g, -5, 5)
            self.m[k] = b1 * self.m[k] + (1 - b1) * g
            self.v[k] = b2 * self.v[k] + (1 - b2) * g * g
            mh = self.m[k] / (1 - b1 ** self.t)
            vh = self.v[k] / (1 - b2 ** self.t)
            p -= lr * mh / (np.sqrt(vh) + 1e-8)

    def copy_from(self, o):
        self.W = [w.copy() for w in o.W]
        self.b = [b.copy() for b in o.b]


# ---------------------------------------------------------------- 환경
class PlacementEnv:
    N_FEAT = 6

    def __init__(self, cm, K):
        self.cm, self.K = cm, K
        self.C = cm.coords
        self.tot = cm.w.sum()
        self.reset()

    def reset(self):
        self.covered = np.zeros(self.cm.n_pts, bool)
        self.sel = []
        self.dist = np.full(len(self.C), 1500.0)
        return self.obs()

    def obs(self):
        cm = self.cm
        newc = ((cm.M & ~self.covered) * cm.w).sum(1) / self.tot * 100
        single = cm.single
        overlap = np.where(single > 0, 1 - newc / np.maximum(single, 1e-9), 0)
        t = len(self.sel)
        phi = np.stack([newc / 10, single / 10, overlap, np.minimum(self.dist, 1500) / 1500,
                        np.full_like(newc, t / self.K), np.full_like(newc, (self.K - t) / self.K)], 1)
        mask = np.zeros(len(self.C), bool)
        mask[self.sel] = True
        self.newc = newc
        return phi, mask

    def summary(self, phi, mask):
        g = np.sort(np.where(mask, -1, phi[:, 0]))[::-1]
        return np.array([self.covered.mean(), phi[0, 4], phi[0, 5], g[0], g[:5].mean(), 1.0])

    def step(self, a):
        r = float(self.newc[a])
        self.sel.append(int(a))
        self.covered |= self.cm.M[a]
        self.dist = np.minimum(self.dist, np.hypot(self.C[:, 0] - self.C[a, 0], self.C[:, 1] - self.C[a, 1]))
        done = len(self.sel) >= self.K
        return self.obs(), r, done


def _softmax_masked(z, mask):
    z = np.where(mask, -np.inf, z)
    z = z - z[~mask].max()
    p = np.exp(z)
    return p / p.sum()


# ---------------------------------------------------------------- PPO
class PPOAgent:
    def __init__(self, seed=0, hidden=32, lr=3e-3, clip=0.2, epochs=4):
        self.rng = np.random.default_rng(seed)
        self.actor = MLP([PlacementEnv.N_FEAT, hidden, hidden, 1], self.rng)
        self.critic = MLP([6, hidden, 1], self.rng)
        self.lr, self.clip, self.epochs = lr, clip, epochs

    def act(self, phi, mask, greedy=False):
        z = self.actor.forward(phi)[:, 0]
        p = _softmax_masked(z, mask)
        a = int(np.argmax(p)) if greedy else int(self.rng.choice(len(p), p=p))
        return a, p[a]

    def run_episode(self, cm, K, greedy=False, record=False):
        env = PlacementEnv(cm, K)
        phi, mask = env.obs()
        traj, total = [], 0.0
        done = False
        while not done:
            a, pa = self.act(phi, mask, greedy)
            st = env.summary(phi, mask)
            (phi2, mask2), r, done = env.step(a)
            if record:
                traj.append((phi, mask, st, a, pa, r))
            total += r
            phi, mask = phi2, mask2
        return env.sel, total, traj

    def train(self, train_cms, K_range=(1, 10), iters=150, episodes=12, log_every=25):
        log = []
        for it in range(1, iters + 1):
            batch = []
            gaps = []
            for _ in range(episodes):
                cm = train_cms[int(self.rng.integers(len(train_cms)))]
                K = int(self.rng.integers(K_range[0], K_range[1] + 1))
                _, R, traj = self.run_episode(cm, K, record=True)
                gaps.append(R - greedy_marginal(cm, K)[1][-1])
                rets = np.cumsum([x[5] for x in traj][::-1])[::-1]      # γ=1 남은 보상합
                batch += [(t[0], t[1], t[2], t[3], t[4], g) for t, g in zip(traj, rets)]
            S = np.stack([b[2] for b in batch])
            G = np.array([b[5] for b in batch])
            V = self.critic.forward(S)[:, 0]
            A = G - V
            A = (A - A.mean()) / (A.std() + 1e-8)
            for _ in range(self.epochs):
                gsum = None
                for (phi, mask, st, a, pa_old, g), adv in zip(batch, A):
                    z = self.actor.forward(phi)[:, 0]
                    p = _softmax_masked(z, mask)
                    ratio = p[a] / pa_old
                    if (adv > 0 and ratio > 1 + self.clip) or (adv < 0 and ratio < 1 - self.clip):
                        continue                                   # clip된 샘플은 기울기 0
                    dz = -ratio * adv * ((np.arange(len(p)) == a) - p)  # −∂(ratio·A)/∂z
                    dz[mask] = 0
                    gr = self.actor.backward(dz[:, None] / len(batch))
                    gsum = gr if gsum is None else [x + y for x, y in zip(gsum, gr)]
                if gsum is not None:
                    self.actor.step(gsum, self.lr)
                V = self.critic.forward(S)[:, 0]
                gc = self.critic.backward(((V - G) / len(G))[:, None] * 2 / 100.0)
                self.critic.step(gc, self.lr)
            log.append(float(np.mean(gaps)))
            if log_every and it % log_every == 0:
                print(f"    [PPO] iter {it:4d}  (RL − greedy) 평균 {np.mean(log[-log_every:]):+.2f}%p", flush=True)
        return log


# ---------------------------------------------------------------- DQN
class DQNAgent:
    def __init__(self, seed=0, hidden=32, lr=2e-3, gamma=1.0, buf=20000, batch=64, target_every=50):
        self.rng = np.random.default_rng(seed)
        self.q = MLP([PlacementEnv.N_FEAT, hidden, hidden, 1], self.rng)
        self.qt = MLP([PlacementEnv.N_FEAT, hidden, hidden, 1], self.rng)
        self.qt.copy_from(self.q)
        self.lr, self.gamma, self.batch, self.target_every = lr, gamma, batch, target_every
        self.buf, self.cap = [], buf

    def act(self, phi, mask, eps=0.0):
        if self.rng.random() < eps:
            return int(self.rng.choice(np.where(~mask)[0]))
        q = self.q.forward(phi)[:, 0]
        q[mask] = -np.inf
        return int(np.argmax(q))

    def run_episode(self, cm, K, eps=0.0, store=False):
        env = PlacementEnv(cm, K)
        phi, mask = env.obs()
        total, done = 0.0, False
        while not done:
            a = self.act(phi, mask, eps)
            (phi2, mask2), r, done = env.step(a)
            if store:
                self.buf.append((phi[a].copy(), r, phi2.copy(), mask2.copy(), done))
                if len(self.buf) > self.cap:
                    self.buf.pop(0)
            total += r
            phi, mask = phi2, mask2
        return env.sel, total

    def train(self, train_cms, K_range=(1, 10), episodes=1500, log_every=250):
        log, step = [], 0
        for ep in range(1, episodes + 1):
            eps = max(0.05, 1.0 - ep / (0.6 * episodes))
            cm = train_cms[int(self.rng.integers(len(train_cms)))]
            K = int(self.rng.integers(K_range[0], K_range[1] + 1))
            _, R = self.run_episode(cm, K, eps, store=True)
            log.append(R - greedy_marginal(cm, K)[1][-1])
            for _ in range(2):
                if len(self.buf) < self.batch:
                    break
                idx = self.rng.choice(len(self.buf), self.batch, replace=False)
                X = np.stack([self.buf[i][0] for i in idx])
                y = []
                for i in idx:
                    _, r, phi2, mask2, done = self.buf[i]
                    if done:
                        y.append(r)
                    else:
                        qn = self.qt.forward(phi2)[:, 0]
                        qn[mask2] = -np.inf
                        y.append(r + self.gamma * qn.max())
                y = np.array(y)
                qp = self.q.forward(X)[:, 0]
                g = self.q.backward(((qp - y) * 2 / len(y))[:, None])
                self.q.step(g, self.lr)
                step += 1
                if step % self.target_every == 0:
                    self.qt.copy_from(self.q)
            if log_every and ep % log_every == 0:
                print(f"    [DQN] ep {ep:5d} ε={eps:.2f}  (RL − greedy) 평균 {np.mean(log[-log_every:]):+.2f}%p", flush=True)
        return log
