#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_rl_fairness.py   (시뮬레이션 0회, 빠른 평가 모델)
================================================================
강화학습 보강 실험: Greedy의 이론 보장이 사라지는 목적에서 비교
  목적 f(S) = 커버(%) × Jain(RSU 기여)        ← 많이 덮으면서 RSU들이 고르게 기여하는 배치
    · RSU 기여: 각 차량점을 그 점을 덮는 RSU들에 1/n씩 나눠 준 합
    · 커버만 볼 때는 submodular(Greedy 63% 보장)지만, Jain을 곱하면 보장이 없어짐
비교: Greedy(커버만) / Greedy(f) / 집합 GA(f) / PPO(f) / DQN(f)
학습: 앞 70% 시간대의 60초 창 10개 → 평가: 전체 + 학습에 안 쓴 뒤 30% 시간대
출력: experiment_results/step4/step4_rl_fairness{tag}.csv(시드 평균), _raw{tag}.csv(시드별), {tag}.png, 학습곡선 csv
실행: python3 step4_rl_fairness.py                                   (짧게: PPO 50 iter, DQN 400 ep, 시드 0)
      python3 step4_rl_fairness.py --ppo-iters 300 --dqn-eps 2500 --seeds 0,1,2 --tag _long   (학습 늘림)
================================================================
"""
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import rsu_lib.rl as RL  # noqa: E402
from rsu_lib.placement import SetGA, greedy_marginal  # noqa: E402
from step4_fixed_algorithms import build_matrices  # noqa: E402
from rsu_lib.surrogate import Surrogate  # noqa: E402

OUT = os.path.join("experiment_results", "step4")


def own_jain(cm, sel):
    if len(sel) == 0:
        return 1.0
    R = cm.M[list(sel)]
    cnt = R.sum(0)
    own = (R / np.maximum(cnt, 1)).sum(1)
    s2 = (own ** 2).sum()
    return float(own.sum() ** 2 / (len(own) * s2)) if s2 > 0 else 0.0


def f_obj(cm, sel):
    return cm.cover(list(sel)) * own_jain(cm, sel)


def greedy_f(cm, K):
    sel = []
    for _ in range(K):
        sel.append(max((i for i in range(len(cm.coords)) if i not in sel), key=lambda i: f_obj(cm, sel + [i])))
    return sel


class FairEnv(RL.PlacementEnv):
    def __init__(self, cm, K):
        self.cur = 0.0
        super().__init__(cm, K)

    def reset(self):
        self.cur = 0.0
        return super().reset()

    def obs(self):
        phi, mask = super().obs()
        df = np.zeros(len(self.C))
        for i in np.where(~mask)[0]:
            df[i] = f_obj(self.cm, self.sel + [int(i)]) - self.cur
        self.df = df
        phi = phi.copy()
        phi[:, 0] = df / 10            # 첫 특징 = 목적함수 증가량(Δf)
        return phi, mask

    def step(self, a):
        r = float(self.df[a])
        self.sel.append(int(a))
        self.covered |= self.cm.M[a]
        self.dist = np.minimum(self.dist, np.hypot(self.C[:, 0] - self.C[a, 0], self.C[:, 1] - self.C[a, 1]))
        self.cur += r
        return self.obs(), r, len(self.sel) >= self.K


class FairGA(SetGA):
    def fit(self, ind):
        self.n_evals += 1
        return f_obj(self.cm, list(ind))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ppo-iters", type=int, default=50)
    ap.add_argument("--dqn-eps", type=int, default=400)
    ap.add_argument("--seeds", default="0", help="강화학습 시드 (예: 0,1,2) → 시드별 결과와 평균")
    ap.add_argument("--tag", default="", help="출력 파일 이름 뒤에 붙일 꼬리표 (예: _long)")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    t0 = time.time()
    S = Surrogate("erlangen.poly.xml", "vehicle_snapshots_2s.csv")
    cm = build_matrices(S)["A"]                       # 교차로 111곳
    sn = pd.read_csv("vehicle_snapshots_2s.csv", encoding="utf-8-sig").snapshot_no.to_numpy()
    cut = np.quantile(sn, 0.7)
    rng = np.random.default_rng(0)
    train = []
    for _ in range(10):
        s0 = rng.integers(sn.min(), cut - 30)
        train.append(cm.subset_points((sn >= s0) & (sn < s0 + 30)))
    test = cm.subset_points(sn >= cut)

    RL.PlacementEnv = FairEnv                          # 강화학습 환경을 공평도 목적으로 교체
    RL.greedy_marginal = lambda c, K: ([], [f_obj(c, greedy_f(c, K))])   # 학습 로그 기준선 = Greedy(f)
    agents = []
    for sd in seeds:
        t1 = time.time()
        print(f"[PPO seed {sd}] 학습 {a.ppo_iters} iter")
        ppo = RL.PPOAgent(seed=sd); lp = ppo.train(train, K_range=(2, 10), iters=a.ppo_iters, episodes=8, log_every=max(1, a.ppo_iters // 4))
        print(f"[DQN seed {sd}] 학습 {a.dqn_eps} episode")
        dqn = RL.DQNAgent(seed=sd); ld = dqn.train(train, K_range=(2, 10), episodes=a.dqn_eps, log_every=max(1, a.dqn_eps // 4))
        agents.append((sd, ppo, dqn, lp, ld))
        print(f"  seed {sd} 학습 {time.time() - t1:.0f}s", flush=True)
    pd.DataFrame({f"PPO_seed{sd}": pd.Series(lp) for sd, _, _, lp, _ in agents}).to_csv(
        os.path.join(OUT, f"step4_rl_fairness_ppo_curve{a.tag}.csv"), index_label="iter")
    pd.DataFrame({f"DQN_seed{sd}": pd.Series(ld) for sd, _, _, _, ld in agents}).to_csv(
        os.path.join(OUT, f"step4_rl_fairness_dqn_curve{a.tag}.csv"), index_label="episode")

    rows = []
    for name, c in (("전체", cm), ("학습 안 쓴 시간대", test)):
        for K in (3, 5, 8, 10):
            sols = {"Greedy(커버만)": greedy_marginal(c, K)[0], "Greedy(f)": greedy_f(c, K)}
            ga = max((FairGA(c, K, pop=40, gens=40, seed=s).run() for s in (0, 1)), key=lambda r: r[1])
            sols["GA(f)"] = ga[0]
            for m, sel in sols.items():
                rows.append(dict(Data=name, K=K, Method=m, Seed=-1, f=round(f_obj(c, sel), 2), Cover=round(c.cover(sel), 2),
                                 Jain_RSU=round(own_jain(c, sel), 3)))
            for sd, ppo, dqn, _, _ in agents:
                for m, sel in (("PPO(f)", ppo.run_episode(c, K, greedy=True)[0]), ("DQN(f)", dqn.run_episode(c, K)[0])):
                    rows.append(dict(Data=name, K=K, Method=m, Seed=sd, f=round(f_obj(c, sel), 2), Cover=round(c.cover(sel), 2),
                                     Jain_RSU=round(own_jain(c, sel), 3)))
    raw = pd.DataFrame(rows)
    raw.to_csv(os.path.join(OUT, f"step4_rl_fairness_raw{a.tag}.csv"), index=False, encoding="utf-8-sig")
    # 시드 평균 (RL), 결정적 방법은 그대로
    df = raw.groupby(["Data", "K", "Method"], as_index=False).agg(f=("f", "mean"), f_std=("f", "std"), Cover=("Cover", "mean"),
                                                                    Jain_RSU=("Jain_RSU", "mean"))
    df = df.round({"f": 2, "f_std": 2, "Cover": 2, "Jain_RSU": 3})
    df.to_csv(os.path.join(OUT, f"step4_rl_fairness{a.tag}.csv"), index=False, encoding="utf-8-sig")
    for name in df.Data.unique():
        print(f"\n== {name}: f = 커버×Jain (괄호: 커버%, Jain)")
        d = df[df.Data == name]
        piv = d.assign(v=d.f.astype(str) + " (" + d.Cover.astype(str) + ", " + d.Jain_RSU.astype(str) + ")").pivot(index="K", columns="Method", values="v")
        print(piv[["Greedy(커버만)", "Greedy(f)", "GA(f)", "PPO(f)", "DQN(f)"]].to_string())

    col = {"Greedy(커버만)": "#b9b8b2", "Greedy(f)": "#2a6fdb", "GA(f)": "#eb6834", "PPO(f)": "#8e44ad", "DQN(f)": "#c0392b"}
    en = {"Greedy(커버만)": "Greedy (coverage only)", "Greedy(f)": "Greedy (f)", "GA(f)": "Set-GA (f)", "PPO(f)": "PPO (f)", "DQN(f)": "DQN (f)"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, name, ttl in zip(axes, ("전체", "학습 안 쓴 시간대"), ("All data", "Held-out time window (not used in training)")):
        d = df[df.Data == name]
        for m in col:
            s = d[d.Method == m]
            ax.plot(s.K, s.f, marker="o", color=col[m], label=en[m], ls="--" if m == "Greedy(커버만)" else "-")
            if m in ("PPO(f)", "DQN(f)") and s.f_std.notna().any():
                ax.fill_between(s.K, s.f - s.f_std, s.f + s.f_std, color=col[m], alpha=0.12)
        ax.set_xlabel("K"); ax.set_ylabel("f = coverage × Jain(RSU)"); ax.grid(color="#e6e5e0")
        ax.set_title(ttl, loc="left", fontsize=11)
    axes[0].legend(frameon=False, fontsize=8)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, f"step4_rl_fairness{a.tag}.png"), dpi=150)
    print(f"\n완료 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
