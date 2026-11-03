#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step4_verify_sim.py   (VM에서 실제 OMNeT++/Veins 시뮬레이션)
================================================================
step4_fixed_algorithms.py 가 만든 배치(step4_placements.csv)를 실제 시뮬레이션으로 검증한다.
  - 같은 좌표 집합은 한 번만 돌림 (예: K≤5에서는 Greedy·PPO·DQN·최적해가 같은 배치)
  - 기존 algo1/algo7 은 step2 결과(5회 평균)를 그대로 가져와 비교
  - 완료된 run은 건너뜀(중단 후 재실행하면 이어서)
출력 (experiment_results/step4/):
  step4_verify_raw.csv       run 1개 = 1행 (모든 지표 + 근사모델 예측값)
  step4_verify_summary.csv   방법×K: 실측 서비스비율/PDR/총수신량/Jain/PER + 예측
  step4_verify_plot.png      K별 실측 서비스 비율 (기존 vs 수정 알고리즘)
실행:  python3 -u step4_verify_sim.py --timeout 300 2>&1 | tee step4_log.txt
       (테스트: --mock / 예정만 보기: --dry-run)
================================================================
"""
import argparse
import json
import os
import socket
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

OUT = os.path.join("experiment_results", "step4")
DEFAULT_METHODS = "Greedy-교차로 (algo1 수정),Greedy-전체교차로 (algo7 수정),GA-집합 (도로점),PPO,DQN,최적해(ILP)"
COLS = ["Key", "Methods", "K", "Rep", "Seed", "Coords", "Pred_Cover", "Success", "Elapsed_Sec", "PDR", "Service_Ratio",
        "Total_Received", "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm", "Metrics_OK", "Error"]
EN = {"Greedy-교차로 (algo1 수정)": "Greedy-intersection (algo1 fixed)", "Greedy-전체교차로 (algo7 수정)": "Greedy-all junctions (algo7 fixed)",
      "GA-집합 (도로점)": "Set-GA (road points)", "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "Optimal (ILP)",
      "algo1 (기존)": "algo1 (old, step2)", "algo7 (기존)": "algo7 (old, step2)"}
COL = {"algo1 (기존)": "#b9b8b2", "algo7 (기존)": "#8d8c86", "Greedy-교차로 (algo1 수정)": "#2a6fdb",
       "Greedy-전체교차로 (algo7 수정)": "#1b998b", "GA-집합 (도로점)": "#eb6834", "PPO": "#8e44ad", "DQN": "#c0392b",
       "최적해(ILP)": "#0b0b0b"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default=DEFAULT_METHODS)
    ap.add_argument("--ks", default="1,2,3,5,8,10")
    ap.add_argument("--repeats", type=int, default=1, help="step2에서 반복 편차가 매우 작아(≤0.13%p) 기본 1회")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()
    raw_path = os.path.join(OUT, "step4_verify_raw.csv")
    P = pd.read_csv(os.path.join(OUT, "step4_placements.csv"), encoding="utf-8-sig")
    methods = [m.strip() for m in a.methods.split(",")]
    ks = [int(k) for k in a.ks.split(",")]

    # 같은 좌표 집합 합치기
    jobs = {}
    for K in ks:
        for m in methods:
            r = P[(P.Method == m) & (P.K == K)]
            if r.empty:
                continue
            c = json.loads(r.Coords.iloc[0])
            key = f"K{K}:" + json.dumps(sorted([[round(x, 1), round(y, 1)] for x, y in c]))
            jobs.setdefault(key, dict(K=K, Coords=c, Methods=[], Pred=float(r.Pred_Cover.iloc[0])))["Methods"].append(m)
    runs = [(k, j, rep) for k, j in jobs.items() for rep in range(a.repeats)]
    print(f"서로 다른 배치 {len(jobs)}개 × 반복 {a.repeats} = {len(runs)} run")
    for k, j in jobs.items():
        print(f"  K={j['K']:2d} 예측 {j['Pred']:5.1f}%  ← {', '.join(j['Methods'])}")
    if a.dry_run:
        return

    if not a.summarize_only:
        if not a.mock:
            try:
                socket.create_connection(("localhost", 9999), timeout=3).close()
            except OSError:
                sys.exit("veins_launchd(localhost:9999)가 안 떠 있어요. 먼저 띄운 뒤 다시 실행하세요.")
        done = set()
        if os.path.exists(raw_path):
            old = pd.read_csv(raw_path)
            done = {(r.Key, int(r.Rep)) for r in old.itertuples() if str(r.Success) == "True"}
        ev = sim_eval.MockEvaluator() if a.mock else sim_eval.SimEvaluator(OUT, "6Mbps", True, a.timeout)
        for i, (key, j, rep) in enumerate(runs, 1):
            if (key, rep) in done:
                continue
            seed = 8000 + 100 * j["K"] + rep
            res = ev.evaluate([tuple(c) for c in j["Coords"]], seed)
            sim_eval.append_csv_row(raw_path, COLS, dict(res, Key=key, Methods="|".join(j["Methods"]), K=j["K"], Rep=rep,
                                                         Seed=seed, Coords=json.dumps(j["Coords"]), Pred_Cover=j["Pred"]))
            print(f"[{i}/{len(runs)}] K={j['K']:2d} 예측 {j['Pred']:5.1f}% → 실측 서비스 {res['Service_Ratio']:.1f}% "
                  f"PDR {res['PDR']:.2f}% {res['Elapsed_Sec']:.0f}s ok={res['Success']}  ({j['Methods'][0]} 외 {len(j['Methods']) - 1})", flush=True)

    # ---------- 요약 ----------
    if not os.path.exists(raw_path):
        return
    raw = pd.read_csv(raw_path)
    raw = raw[raw.Success.astype(str) == "True"]
    met = ["Service_Ratio", "PDR", "Total_Received", "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm"]
    rows = []
    for _, r in raw.groupby("Key").agg({**{m: "mean" for m in met}, "K": "first", "Methods": "first", "Pred_Cover": "first"}).iterrows():
        for m in r.Methods.split("|"):
            rows.append(dict(Method=m, K=int(r.K), Pred_Cover=r.Pred_Cover, **{x: r[x] for x in met}))
    s2 = os.path.join("experiment_results", "step2", "step2_summary_by_K.csv")
    if os.path.exists(s2):
        b = pd.read_csv(s2)
        b = b[b.Phase == "sweep"]
        old_pred = {}
        pp = P[P.Method.isin(["algo1 (기존)", "algo7 (기존)"])]
        for r in pp.itertuples():
            old_pred[(r.Method, r.K)] = r.Pred_Cover
        for r in b.itertuples():
            lab = f"{r.Algo} (기존)"
            if int(r.K) in ks:
                rows.append(dict(Method=lab, K=int(r.K), Pred_Cover=old_pred.get((lab, int(r.K))),
                                 **{m: getattr(r, m + "_mean") for m in met}))
    S = pd.DataFrame(rows).sort_values(["K", "Method"])
    S.to_csv(os.path.join(OUT, "step4_verify_summary.csv"), index=False, encoding="utf-8-sig")
    print(S.round(2).to_string(index=False))
    if len(S.dropna(subset=["Pred_Cover"])) > 2:
        v = S.dropna(subset=["Pred_Cover"])
        print(f"\n예측 vs 실측 서비스 비율: r={np.corrcoef(v.Pred_Cover, v.Service_Ratio)[0, 1]:.3f}, "
              f"평균오차 {np.mean(np.abs(v.Pred_Cover - v.Service_Ratio)):.2f}%p")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    for m in [x for x in COL if x in set(S.Method)]:
        s = S[S.Method == m].sort_values("K")
        ls = "--" if "기존" in m else "-"
        axes[0].plot(s.K, s.Service_Ratio, marker="o", ms=4, ls=ls, color=COL[m], label=EN[m])
        axes[1].plot(s.K, s.PDR, marker="o", ms=4, ls=ls, color=COL[m], label=EN[m])
    axes[0].set_ylabel("Measured service ratio (%)"); axes[1].set_ylabel("Measured PDR (%)")
    for ax, t in zip(axes, ("Service ratio (OMNeT++/Veins)", "PDR (OMNeT++/Veins)")):
        ax.set_xlabel("K (number of RSUs)"); ax.grid(color="#e6e5e0"); ax.set_title(t, loc="left", fontsize=11)
    axes[0].legend(frameon=False, fontsize=8)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_verify_plot.png"), dpi=150)
    print("저장:", OUT)


if __name__ == "__main__":
    main()
