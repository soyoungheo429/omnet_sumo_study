#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step3b_ga_lastgen_combos.py
================================================================
GA 마지막 세대 상위 좌표들을 조합해 다중 RSU(K=2..5)로 돌려본다. (시뮬레이션 K=2..5 → 기본 26회)
  - 마지막 세대 상위 N개는 서로 11~95 m 안에 몰려 있어서, 그대로 K개를 뽑으면 사실상 같은 자리.
    그래서 (a) 'top'  : PDR 순으로 그냥 상위 K개
          (b) 'diverse': PDR 순으로 보되 이미 뽑은 점과 --min-sep(기본 300 m) 이상 떨어진 것만 선택
    두 방식을 비교한다. 후보가 모자라면 전체 세대 기록에서 이어서 채운다.
  - 기준선: 단일 최적점(K=1) 1회.
출력: experiment_results/step3/step3b_combos_raw.csv, step3b_combos_summary.csv, step3b_combos.png
실행:  python3 step3b_ga_lastgen_combos.py [--mock] [--ks 2,3,4,5] [--repeats 1]
================================================================
"""
import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib import sim_eval  # noqa: E402

DEFAULT_CSV = os.path.join("experiment_results", "single", "algo4", "algo4_GA_hybrid_corrected",
                           "ga_hybrid_final_results_corrected.csv")
COLS = ["Mode", "K", "Rep", "Seed", "Coords", "Success", "Elapsed_Sec", "PDR", "Service_Ratio", "Total_Received",
        "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm", "SNR_Mean_dB", "Metrics_OK", "Error"]
METRICS = ["PDR", "Service_Ratio", "Total_Received", "Jain_RSU", "PER", "Collisions", "RSSI_Mean_dBm"]


def pick(cands, k, min_sep):
    """cands: PDR 내림차순 [(x,y), ...]. min_sep 이상 떨어진 점만 k개."""
    out = []
    for p in cands:
        if all(np.hypot(p[0] - q[0], p[1] - q[1]) >= min_sep for q in out):
            out.append(p)
        if len(out) == k:
            return out
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--out", default=os.path.join("experiment_results", "step3"))
    ap.add_argument("--ks", default="2,3,4,5")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-top-k", type=int, default=99, help="top 방식은 이 K까지만 실행 (겹친 좌표 3개 이상에서 시뮬이 멈추는 문제 회피)")
    ap.add_argument("--min-sep", type=float, default=300.0)
    ap.add_argument("--bitrate", default="6Mbps")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    raw_path = os.path.join(a.out, "step3b_combos_raw.csv")

    d = pd.read_csv(a.csv, encoding="utf-8-sig")
    last = d[d.Gen == d.Gen.max()].sort_values("PDR", ascending=False)
    rest = d[d.Gen != d.Gen.max()].sort_values("PDR", ascending=False)
    ordered = [(round(r.Sim_X, 2), round(r.Sim_Y, 2)) for r in pd.concat([last, rest]).itertuples()]
    ks = [int(x) for x in a.ks.split(",")]

    # 실행 계획
    plan = [("single", 1, [ordered[0]])]
    for k in ks:
        top = ordered[:k]
        if k <= a.max_top_k:
            plan.append(("top", k, top))
        div = pick(ordered, k, a.min_sep)
        if div is None:
            print(f"[경고] K={k}: min-sep {a.min_sep} m 를 만족하는 점이 부족해서 diverse 생략")
        else:
            plan.append(("diverse", k, div))
    runs = [(m, k, c, r) for (m, k, c) in plan for r in range(a.repeats)]
    print(f"총 {len(runs)} run (repeats={a.repeats})")
    for m, k, c in plan:
        print(f"  {m:8s} K={k}: {c}")
    if a.dry_run:
        return

    done = set()
    if os.path.exists(raw_path):
        old = pd.read_csv(raw_path)
        done = {(r.Mode, r.K, r.Rep) for r in old.itertuples() if str(r.Success) == "True"}
    ev = sim_eval.MockEvaluator() if a.mock else sim_eval.SimEvaluator(a.out, a.bitrate, True, a.timeout)

    for i, (m, k, c, r) in enumerate(runs, 1):
        if (m, k, r) in done:
            continue
        seed = 7000 + 10 * k + r
        res = ev.evaluate(c, seed)
        row = dict(res, Mode=m, K=k, Rep=r, Seed=seed, Coords=json.dumps(c))
        sim_eval.append_csv_row(raw_path, COLS, row)
        print(f"[{i}/{len(runs)}] {m:8s} K={k} rep{r} PDR={res['PDR']:.2f}% Svc={res['Service_Ratio']:.1f}% "
              f"{res['Elapsed_Sec']:.0f}s ok={res['Success']}", flush=True)

    # 요약
    raw = pd.read_csv(raw_path)
    raw = raw[raw.Success.astype(str) == "True"]
    summ = raw.groupby(["Mode", "K"])[METRICS].mean().round(3).reset_index()
    summ["N"] = raw.groupby(["Mode", "K"]).size().values
    summ.to_csv(os.path.join(a.out, "step3b_combos_summary.csv"), index=False, encoding="utf-8-sig")
    print(summ.to_string(index=False))

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    base = summ[summ.Mode == "single"]
    for ax, met in zip(axes, ["PDR", "Service_Ratio", "Total_Received"]):
        for mode, color in [("top", "#2a6fdb"), ("diverse", "#eb6834")]:
            s = summ[summ.Mode == mode]
            ax.plot(s.K, s[met], marker="o", color=color, label=mode)
        if len(base):
            ax.axhline(base[met].iloc[0], color="#52514e", ls="--", lw=1, label="single best (K=1)")
        ax.set_xlabel("K"); ax.set_title(met, loc="left"); ax.grid(color="#e6e5e0")
    axes[0].legend(frameon=False)
    plt.tight_layout()
    plt.savefig(os.path.join(a.out, "step3b_combos.png"), dpi=140)
    print("저장:", a.out)


if __name__ == "__main__":
    main()
