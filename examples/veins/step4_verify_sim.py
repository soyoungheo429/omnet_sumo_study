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
  step4_verify_table.csv/.md 방법×K × 지표 10개 표 (PDR, 총수신량, 서비스비율, Jain RSU/차량, RSSI, PER, 충돌, 채널점유율)
  step4_verify_metrics_grid.png  지표 9개 × K 그래프 (기존 = 점선)
  step4_verify_pred_vs_meas.png  근사모델 예측 vs 실측 서비스 비율
실행:  python3 -u step4_verify_sim.py --timeout 300 2>&1 | tee step4_log.txt
       표·그래프만 다시 만들기: python3 step4_verify_sim.py --summarize-only
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
        "Total_Received", "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm", "SNR_Mean_dB",
        "Channel_Busy", "RXTX_Lost", "Metrics_OK", "Error"]
# 표/그래프에 쓰는 지표 (순서 = 표 열 순서)
METRICS = [("PDR", "PDR(%)"), ("Total_Received", "총 수신량"), ("Service_Ratio", "서비스 비율(%)"),
           ("Jain_RSU", "Jain RSU"), ("Jain_Vehicle", "Jain 차량"), ("RSSI_Mean_dBm", "RSSI(dBm)"),
           ("PER", "PER(%)"), ("Collisions", "충돌 수"), ("Channel_Busy", "채널 점유율(%)")]
METRICS_EN = {"PDR": "PDR (%)", "Total_Received": "Total received BSMs", "Service_Ratio": "Service ratio (%)",
              "Jain_RSU": "Jain index (RSU)", "Jain_Vehicle": "Jain index (vehicle)", "RSSI_Mean_dBm": "Mean RSSI (dBm)",
              "PER": "PER (%)", "Collisions": "Collisions", "Channel_Busy": "Channel busy (%)"}
EN = {"Greedy-교차로 (algo1 수정)": "Greedy-intersection (algo1 fixed)", "Greedy-전체교차로 (algo7 수정)": "Greedy-all junctions (algo7 fixed)",
      "GA-집합 (도로점)": "Set-GA (road points)", "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "Optimal (ILP)",
      "algo1 (기존)": "algo1 (old, step2)", "algo7 (기존)": "algo7 (old, step2)"}
COL = {"algo1 (기존)": "#b9b8b2", "algo7 (기존)": "#8d8c86", "Greedy-교차로 (algo1 수정)": "#2a6fdb",
       "Greedy-전체교차로 (algo7 수정)": "#1b998b", "GA-집합 (도로점)": "#eb6834", "PPO": "#8e44ad", "DQN": "#c0392b",
       "최적해(ILP)": "#0b0b0b"}


def migrate_raw(path):
    """옛 버전(열 개수가 다른) 헤더로 시작된 raw CSV를 현재 COLS 형식으로 맞춘다. 이미 돌린 run은 그대로 보존."""
    if not os.path.exists(path):
        return
    import csv
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] == COLS:
        return
    head = rows[0]
    fixed = []
    for r in rows[1:]:
        if len(r) == len(COLS):          # 새 버전으로 쓴 줄
            fixed.append(dict(zip(COLS, r)))
        else:                            # 옛 헤더 기준 줄
            fixed.append(dict(zip(head, r)))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(fixed)
    print(f"[정리] {path}: 옛 형식 헤더를 새 형식({len(COLS)}열)으로 맞춤, {len(fixed)}줄 보존")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default=DEFAULT_METHODS)
    ap.add_argument("--ks", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--repeats", type=int, default=1, help="step2에서 반복 편차가 매우 작아(≤0.13%p) 기본 1회")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()
    raw_path = os.path.join(OUT, "step4_verify_raw.csv")
    migrate_raw(raw_path)
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
    met = [m for m, _ in METRICS]
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

    # ---------- 표 (Excel/Notion용) ----------
    T = S[["Method", "K"] + met + ["Pred_Cover"]].copy()
    T.columns = ["방법", "K"] + [k for _, k in METRICS] + ["예측 커버(%)"]
    T = T.round({"PDR(%)": 2, "총 수신량": 0, "서비스 비율(%)": 2, "Jain RSU": 3, "Jain 차량": 3, "RSSI(dBm)": 2,
                 "PER(%)": 3, "충돌 수": 1, "채널 점유율(%)": 2, "예측 커버(%)": 1})
    T.to_csv(os.path.join(OUT, "step4_verify_table.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(OUT, "step4_verify_table.md"), "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(T.columns) + " |\n|" + "---|" * len(T.columns) + "\n")
        for r in T.itertuples(index=False):
            f.write("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |\n")

    # ---------- 그래프: 지표 9개 × K ----------
    fig, axes = plt.subplots(3, 3, figsize=(15, 11))
    order = [x for x in COL if x in set(S.Method)]
    for ax, (m_key, _) in zip(axes.ravel(), METRICS):
        for m in order:
            s = S[S.Method == m].sort_values("K")
            ls = "--" if "기존" in m else "-"
            ax.plot(s.K, s[m_key], marker="o", ms=3.5, lw=1.6, ls=ls, color=COL[m], label=EN[m])
        ax.set_title(METRICS_EN[m_key], loc="left", fontsize=11)
        ax.set_xlabel("K (number of RSUs)"); ax.grid(color="#e6e5e0")
    axes[0, 0].legend(frameon=False, fontsize=7.5)
    fig.suptitle("Step4 verification in OMNeT++/Veins: all metrics vs K (dashed = old algorithms from step2)",
                 x=0.01, ha="left", fontsize=12)
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_verify_metrics_grid.png"), dpi=150); plt.close()

    # 예측 vs 실측 산점도
    v = S.dropna(subset=["Pred_Cover"])
    if len(v) > 2:
        fig, ax = plt.subplots(figsize=(5, 4.8))
        for m in order:
            s = v[v.Method == m]
            ax.scatter(s.Pred_Cover, s.Service_Ratio, s=22, color=COL[m], label=EN[m])
        lim = max(v.Pred_Cover.max(), v.Service_Ratio.max()) + 3
        ax.plot([0, lim], [0, lim], color="#52514e", ls="--", lw=1)
        ax.set_xlabel("Surrogate prediction (%)"); ax.set_ylabel("Measured service ratio (%)")
        ax.set_title(f"Prediction vs simulation  r={np.corrcoef(v.Pred_Cover, v.Service_Ratio)[0, 1]:.3f}", loc="left", fontsize=11)
        ax.grid(color="#e6e5e0"); ax.legend(frameon=False, fontsize=7)
        plt.tight_layout(); plt.savefig(os.path.join(OUT, "step4_verify_pred_vs_meas.png"), dpi=150); plt.close()
    print("저장:", OUT)


if __name__ == "__main__":
    main()
