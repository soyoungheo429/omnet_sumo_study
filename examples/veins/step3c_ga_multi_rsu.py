#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step3c_ga_multi_rsu.py
================================================================
다중 RSU GA. 개체 = K개 RSU 좌표(2K개 유전자). 적합도 = Service_Ratio(%) (기본).
  * 평균 PDR을 적합도로 쓰면 RSU를 전부 최고점 한 곳에 쌓는 게 유리해져서 부적절 → 서비스 비율 사용.
    (--fitness Total_Received / PDR 로 바꿀 수 있음)
  * GA 반복은 K마다 --runs 회 (기본 2회). 개체군 --pop(8) x 세대 --gens(6), 엘리트 2.
  * 초기 개체군: 절반은 지도 전체 균등 랜덤, 절반은 algo1 후보 좌표(+100 m 지터)에서 뽑음.
  * 한 run 안에서는 시뮬레이션 seed 를 고정(평가 잡음 제거), run 마다 seed 가 다름.
  * 같은 좌표는 캐시해서 재평가하지 않음.
출력 (experiment_results/step3/):
  step3c_ga_evals.csv      (평가 1회=1행: K, Run, Gen, Ind, 좌표, 지표)
  step3c_ga_runs.csv       (run 요약: 최종 최적 좌표/지표, 평가 횟수, 시뮬 시간, 총 시간)
  step3c_ga_vs_step2.csv   (같은 K에서 step2의 algo1/algo7 과 비교)
  step3c_ga_convergence.png
실행:  python3 step3c_ga_multi_rsu.py [--mock] [--ks 2,3,5] [--runs 2]
================================================================
"""
import argparse
import json
import os
import random
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
from rsu_lib import sim_eval  # noqa: E402

EV_COLS = ["K", "Run", "Gen", "Ind", "Seed", "Coords", "Fitness", "Success", "Elapsed_Sec", "PDR", "Service_Ratio",
           "Total_Received", "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm", "Metrics_OK", "Error"]
RUN_COLS = ["K", "Run", "Fitness_Name", "Best_Fitness", "Best_Coords", "PDR", "Service_Ratio", "Total_Received",
            "Jain_RSU", "PER", "Collisions", "RSSI_Mean_dBm", "N_Evals", "Sim_Sec", "Wall_Sec", "Pop", "Gens"]


def clip(p):
    return (float(np.clip(p[0], sim_eval.X_MIN, sim_eval.X_MAX)), float(np.clip(p[1], sim_eval.Y_MIN, sim_eval.Y_MAX)))


def load_candidates(path="final_selected_rsus_algo1_corrected.csv", n=30):
    try:
        c = pd.read_csv(path, encoding="utf-8-sig").head(n)
        return [(float(r.Sim_X), float(r.Sim_Y)) for r in c.itertuples()]
    except Exception:
        return []


def init_pop(rng, pop, k, cands):
    out = []
    for i in range(pop):
        if cands and i % 2 == 1:
            ind = [clip((x + rng.gauss(0, 100), y + rng.gauss(0, 100))) for x, y in rng.sample(cands, min(k, len(cands)))]
            while len(ind) < k:
                ind.append((rng.uniform(sim_eval.X_MIN, sim_eval.X_MAX), rng.uniform(sim_eval.Y_MIN, sim_eval.Y_MAX)))
        else:
            ind = [(rng.uniform(sim_eval.X_MIN, sim_eval.X_MAX), rng.uniform(sim_eval.Y_MIN, sim_eval.Y_MAX))
                   for _ in range(k)]
        out.append(ind)
    return out


def crossover(rng, a, b):
    child = []
    for pa, pb in zip(a, b):
        t = rng.random()
        child.append(clip((t * pa[0] + (1 - t) * pb[0], t * pa[1] + (1 - t) * pb[1])) if rng.random() < 0.5
                     else (pa if rng.random() < 0.5 else pb))
    return child


def mutate(rng, ind, sigma, rate=0.3):
    out = []
    for p in ind:
        if rng.random() < rate:
            p = clip((p[0] + rng.gauss(0, sigma), p[1] + rng.gauss(0, sigma)))
        out.append(p)
    return out


def tournament(rng, scored, n=3):
    return max(rng.sample(scored, min(n, len(scored))), key=lambda t: t[0])[1]


def run_ga(k, run, a, ev, cands, evals_path):
    seed = 9000 + 100 * k + run
    rng = random.Random(seed)
    cache, n_evals, sim_sec = {}, 0, 0.0
    t0 = time.time()

    def fit(ind, gen, idx):
        nonlocal n_evals, sim_sec
        key = tuple((round(x, 1), round(y, 1)) for x, y in sorted(ind))
        if key in cache:
            return cache[key]
        res = ev.evaluate(list(ind), seed)
        n_evals += 1
        sim_sec += res.get("Elapsed_Sec", 0.0) or 0.0
        f = res.get(a.fitness, float("nan")) if res.get("Success") else -1.0
        f = -1.0 if f != f else f
        row = dict(res, K=k, Run=run, Gen=gen, Ind=idx, Seed=seed, Coords=json.dumps([list(map(float, p)) for p in ind]),
                   Fitness=f)
        sim_eval.append_csv_row(evals_path, EV_COLS, row)
        cache[key] = (f, res)
        return cache[key]

    pop = init_pop(rng, a.pop, k, cands)
    best = (-1e18, None, None)
    hist = []
    for g in range(1, a.gens + 1):
        scored = []
        for i, ind in enumerate(pop):
            f, res = fit(ind, g, i)
            scored.append((f, ind, res))
        scored.sort(key=lambda t: -t[0])
        if scored[0][0] > best[0]:
            best = scored[0]
        hist.append(best[0])
        print(f"  K={k} run{run} gen{g}/{a.gens} best={best[0]:.2f} (이번 세대 {scored[0][0]:.2f}) 평가 {n_evals}회", flush=True)
        if g == a.gens:
            break
        sigma = 200.0 * (1 - 0.7 * g / a.gens)
        nxt = [list(t[1]) for t in scored[:a.elite]]
        pairs = [(f, ind) for f, ind, _ in scored]
        while len(nxt) < a.pop:
            nxt.append(mutate(rng, crossover(rng, tournament(rng, pairs), tournament(rng, pairs)), sigma))
        pop = nxt
    f, ind, res = best
    summary = {"K": k, "Run": run, "Fitness_Name": a.fitness, "Best_Fitness": round(f, 4),
               "Best_Coords": json.dumps([[round(x, 1), round(y, 1)] for x, y in ind]),
               "N_Evals": n_evals, "Sim_Sec": round(sim_sec, 1), "Wall_Sec": round(time.time() - t0, 1),
               "Pop": a.pop, "Gens": a.gens}
    for m in ["PDR", "Service_Ratio", "Total_Received", "Jain_RSU", "PER", "Collisions", "RSSI_Mean_dBm"]:
        summary[m] = res.get(m)
    return summary, hist


def compare_with_step2(out, ks):
    p = os.path.join("experiment_results", "step2", "step2_runs_raw.csv")
    runs = pd.read_csv(os.path.join(out, "step3c_ga_runs.csv"))
    ga = runs.groupby("K")[["PDR", "Service_Ratio", "Total_Received", "Jain_RSU", "PER", "RSSI_Mean_dBm"]].mean()
    rows = [dict(Algo="GA_multi", K=k, **r.to_dict()) for k, r in ga.iterrows()]
    if os.path.exists(p):
        s = pd.read_csv(p)
        s = s[(s.Phase == "sweep") & (s.Success.astype(str) == "True") & (s.Sync.astype(str) == "True")]
        g = s[s.K.isin(ks)].groupby(["Algo", "K"])[["PDR", "Service_Ratio", "Total_Received", "Jain_RSU", "PER",
                                                      "RSSI_Mean_dBm"]].mean()
        rows += [dict(Algo=al, K=k, **r.to_dict()) for (al, k), r in g.iterrows()]
    else:
        print("[안내] step2 결과가 없어 비교 표에는 GA만 들어갑니다 (step2 끝난 뒤 --compare-only 로 다시 만들 수 있어요)")
    df = pd.DataFrame(rows).sort_values(["K", "Algo"]).round(3)
    df.to_csv(os.path.join(out, "step3c_ga_vs_step2.csv"), index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("experiment_results", "step3"))
    ap.add_argument("--ks", default="2,3,5")
    ap.add_argument("--runs", type=int, default=2, help="K마다 GA 반복 횟수 (기본 2)")
    ap.add_argument("--pop", type=int, default=8)
    ap.add_argument("--gens", type=int, default=6)
    ap.add_argument("--elite", type=int, default=2)
    ap.add_argument("--fitness", default="Service_Ratio", choices=["Service_Ratio", "Total_Received", "PDR"])
    ap.add_argument("--bitrate", default="6Mbps")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--compare-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ks = [int(x) for x in a.ks.split(",")]
    evals_path = os.path.join(a.out, "step3c_ga_evals.csv")
    runs_path = os.path.join(a.out, "step3c_ga_runs.csv")
    if a.compare_only:
        compare_with_step2(a.out, ks)
        return

    done = set()
    if os.path.exists(runs_path):
        old = pd.read_csv(runs_path)
        done = {(int(r.K), int(r.Run)) for r in old.itertuples()}
    ev = sim_eval.MockEvaluator() if a.mock else sim_eval.SimEvaluator(a.out, a.bitrate, True, a.timeout)
    cands = load_candidates()
    print(f"GA: K={ks}, 반복 {a.runs}회, pop {a.pop} x gens {a.gens}, 적합도 {a.fitness}  (run당 최대 약 "
          f"{a.pop + (a.gens - 1) * (a.pop - a.elite)}회 평가)")
    curves = {}
    for k in ks:
        for run in range(a.runs):
            if (k, run) in done:
                print(f"K={k} run{run}: 이미 완료, 건너뜀")
                continue
            summ, hist = run_ga(k, run, a, ev, cands, evals_path)
            sim_eval.append_csv_row(runs_path, RUN_COLS, summ)
            curves[(k, run)] = hist
            print(f"== K={k} run{run} 완료: {a.fitness}={summ['Best_Fitness']} 평가 {summ['N_Evals']}회 "
                  f"{summ['Wall_Sec']:.0f}s 좌표 {summ['Best_Coords']}", flush=True)

    # 수렴 그림 (평가 CSV 에서 세대별 best 누적)
    if os.path.exists(evals_path):
        e = pd.read_csv(evals_path)
        fig, ax = plt.subplots(figsize=(6.5, 4))
        for (k, run), s in e.groupby(["K", "Run"]):
            g = s.groupby("Gen").Fitness.max().cummax()
            ax.plot(g.index, g.values, marker="o", ms=3, label=f"K={k} run{run}")
        ax.set_xlabel("Generation"); ax.set_ylabel(a.fitness); ax.grid(color="#e6e5e0")
        ax.legend(frameon=False, fontsize=8); ax.set_title("Multi-RSU GA convergence", loc="left")
        plt.tight_layout(); plt.savefig(os.path.join(a.out, "step3c_ga_convergence.png"), dpi=140)
    if os.path.exists(runs_path):
        compare_with_step2(a.out, ks)


if __name__ == "__main__":
    main()
