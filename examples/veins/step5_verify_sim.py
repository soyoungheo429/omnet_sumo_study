#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step5_verify_sim.py   (VM에서 실제 OMNeT++/Veins 시뮬레이션, 반복 R회)
================================================================
step5_placements.py 의 배치를 교통 패턴별로 실제 시뮬레이션 R회(기본 5) 돌려 평균·표준편차를 낸다.
  - 시나리오마다 다른 지도·교통: <지도>_P*.launchd.xml 로 바꿔 끼움 (Erlangen P1..P3 / Darmstadt DA_P1..DA_P3)
  - 같은 좌표 집합은 한 번만 (K가 작을 때 Greedy/PPO/DQN/ILP가 같은 배치인 경우)
  - 반복 r의 seed = 9000 + r  → 모든 방법이 같은 seed 세트로 비교됨 (짝지은 비교/검정 가능)
  - 순서: 반복 0을 모든 패턴·K·방법에 대해 먼저 → 반복 1 → ...  (중간에 멈춰도 반복 수만 적은 완결 결과)
  - 완료된 run은 건너뜀 (중단 후 같은 명령으로 이어서)
출력 (experiment_results/step5/):
  step5_verify_raw.csv      run 1개 = 1행 (패턴, K, 반복, seed, 모든 지표, 시뮬 시간)
  step5_verify_summary.csv  패턴×방법×K: 지표별 n / 평균 / 표준편차 / 95% 신뢰구간
실행:  python3 -u step5_verify_sim.py --timeout 600 2>&1 | tee step5_log.txt
       Darmstadt: python3 -u step5_verify_sim.py --patterns DA_P1,DA_P2,DA_P3 --ks 1,2,3,4,5,6,7,8,9,10 --timeout 600
       예정만 보기: --dry-run   /  요약만: --summarize-only   /  테스트: --mock
================================================================
"""
import argparse
import json
import math
import os
import re
import socket
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib import sim_eval  # noqa: E402
from rsu_lib import scenario as SC  # noqa: E402

OUT = os.path.join("experiment_results", "step5")
RAW = os.path.join(OUT, "step5_verify_raw.csv")
DEFAULT_METHODS = ("Grid top-K,Greedy-교차로,Greedy-전체교차로,GA-집합 (도로점),GA-연속그룹,GA-연속그룹 (기존 연산),PPO,DQN,최적해(ILP)")
COLS = ["Key", "Pattern", "Methods", "K", "Rep", "Seed", "Coords", "Pred_Cover", "Success", "Elapsed_Sec", "PDR",
        "Service_Ratio", "Total_Received", "Jain_RSU", "Jain_Vehicle", "PER", "Collisions", "RSSI_Mean_dBm",
        "SNR_Mean_dB", "Channel_Busy", "RXTX_Lost", "Metrics_OK", "Error"]
METRICS = ["Service_Ratio", "PDR", "Total_Received", "Jain_RSU", "Jain_Vehicle", "RSSI_Mean_dBm", "PER",
           "Collisions", "Channel_Busy", "Elapsed_Sec"]
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def make_eval(p, timeout):
    """시나리오별 템플릿: launchConfig 줄만 <지도>_P*.launchd.xml 로 교체"""
    d = os.path.join(OUT, p)
    ev = sim_eval.SimEvaluator(d, "6Mbps", True, timeout)
    txt = open(ev.template, encoding="utf-8").read()
    txt, n = re.subn(r'^\*\.manager\.launchConfig\s*=.*$', f'*.manager.launchConfig = xmldoc("{SC.files(p)["launchd"]}")  # [step5]',
                     txt, flags=re.M)
    if n != 1:
        sys.exit("템플릿에서 launchConfig 줄을 찾지 못함")
    open(ev.template, "w", encoding="utf-8").write(txt)
    return ev


def place_key(p, K, coords):
    return f"{p}|K{K}|" + json.dumps(sorted([[round(x, 1), round(y, 1)] for x, y in coords]))


def summarize(pats):
    """방법 이름은 현재 placements.csv 기준으로 붙임 (다시 돌린 방법의 옛 결과가 섞이지 않게)"""
    raw = pd.read_csv(RAW)
    raw = raw[raw.Success.astype(str) == "True"]
    owners = {}
    for p in pats:
        P = pd.read_csv(os.path.join(OUT, p, "placements.csv"), encoding="utf-8-sig")
        for r in P.itertuples():
            owners.setdefault(place_key(p, int(r.K), json.loads(r.Coords)), []).append(r.Method)
    rows = []
    for key, g in raw.groupby("Key"):
        if key not in owners:
            continue
        base = dict(Key=key, Pattern=g.Pattern.iloc[0], K=int(g.K.iloc[0]), Pred_Cover=g.Pred_Cover.iloc[0], n=len(g))
        stats = {}
        for m in METRICS:
            v = g[m].astype(float).to_numpy()
            sd = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
            stats.update({f"{m}_mean": v.mean(), f"{m}_std": sd,
                          f"{m}_ci95": T95.get(len(v) - 1, 1.96) * sd / math.sqrt(len(v)) if len(v) > 1 else 0.0})
        for m in owners[key]:
            rows.append(dict(base, Method=m, **stats))
    S = pd.DataFrame(rows).sort_values(["Pattern", "K", "Method"])
    S.to_csv(os.path.join(OUT, "step5_verify_summary.csv"), index=False, encoding="utf-8-sig")
    show = S[["Pattern", "K", "Method", "n", "Pred_Cover", "Service_Ratio_mean", "Service_Ratio_std", "PDR_mean", "Jain_RSU_mean"]]
    print(show.round(2).to_string(index=False))
    return S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patterns", default="P1,P2,P3")
    ap.add_argument("--methods", default=DEFAULT_METHODS)
    ap.add_argument("--ks", default="1,3,5,8,10")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    a = ap.parse_args()
    pats = a.patterns.split(",")
    methods = [m.strip() for m in a.methods.split(",")]
    ks = [int(k) for k in a.ks.split(",")]

    jobs = {}  # key -> job
    for p in pats:
        P = pd.read_csv(os.path.join(OUT, p, "placements.csv"), encoding="utf-8-sig")
        for K in ks:
            for m in methods:
                r = P[(P.Method == m) & (P.K == K)]
                if r.empty:
                    continue
                c = json.loads(r.Coords.iloc[0])
                key = place_key(p, K, c)
                jobs.setdefault(key, dict(Pattern=p, K=K, Coords=c, Methods=[], Pred=float(r.Pred_Cover.iloc[0])))["Methods"].append(m)
    order = sorted(jobs, key=lambda k: (pats.index(jobs[k]["Pattern"]), jobs[k]["K"]))
    runs = [(k, rep) for rep in range(a.repeats) for k in order]
    print(f"패턴 {pats}, K {ks}: 서로 다른 배치 {len(jobs)}개 × 반복 {a.repeats} = {len(runs)} run")
    for p in pats:
        n = sum(1 for j in jobs.values() if j["Pattern"] == p)
        print(f"  {p}: 배치 {n}개")
    if a.dry_run:
        for k in order:
            j = jobs[k]
            print(f"  {j['Pattern']} K={j['K']:2d} 예측 {j['Pred']:5.1f}% ← {', '.join(j['Methods'])}")
        return
    if not a.summarize_only:
        if not a.mock:
            try:
                socket.create_connection(("localhost", 9999), timeout=3).close()
            except OSError:
                sys.exit("veins_launchd(localhost:9999)가 안 떠 있어요. 먼저 띄운 뒤 다시 실행하세요.")
        done = set()
        if os.path.exists(RAW):
            old = pd.read_csv(RAW)
            done = {(r.Key, int(r.Rep)) for r in old.itertuples() if str(r.Success) == "True"}
        evs = {p: (sim_eval.MockEvaluator() if a.mock else make_eval(p, a.timeout)) for p in pats}
        todo = [(k, rep) for k, rep in runs if (k, rep) not in done]
        print(f"남은 run {len(todo)}개", flush=True)
        el = []
        for i, (key, rep) in enumerate(todo, 1):
            j = jobs[key]
            seed = 9000 + rep
            res = evs[j["Pattern"]].evaluate([tuple(c) for c in j["Coords"]], seed)
            sim_eval.append_csv_row(RAW, COLS, dict(res, Key=key, Pattern=j["Pattern"], Methods="|".join(j["Methods"]),
                                                    K=j["K"], Rep=rep, Seed=seed, Coords=json.dumps(j["Coords"]),
                                                    Pred_Cover=j["Pred"]))
            el.append(res["Elapsed_Sec"])
            eta = np.mean(el) * (len(todo) - i) / 3600
            print(f"[{i}/{len(todo)}] rep{rep} {j['Pattern']} K={j['K']:2d} 예측 {j['Pred']:5.1f}% → 서비스 {res['Service_Ratio']:.1f}% "
                  f"PDR {res['PDR']:.2f}% {res['Elapsed_Sec']:.0f}s ok={res['Success']}  남은 ~{eta:.1f}h  ({j['Methods'][0]} 외 {len(j['Methods']) - 1})",
                  flush=True)
    if os.path.exists(RAW):   # 요약은 배치가 있는 모든 시나리오 (Erlangen + Darmstadt 함께)
        allp = sorted(d for d in os.listdir(OUT) if os.path.exists(os.path.join(OUT, d, "placements.csv")))
        summarize(allp)


if __name__ == "__main__":
    main()
