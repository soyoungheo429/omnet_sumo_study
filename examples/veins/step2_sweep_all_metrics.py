#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step2_sweep_all_metrics.py
================================================================
2단계: 전체 지표(PDR/수신총량/서비스율/Jain/PER/충돌/RSSI/SNR/채널점유율/RSU별 수신량)로
  A) isolated : 후보 RSU를 하나씩 단독(K=1) 측정          → RSU별 간섭 손실 계산용 기준선
  B) sweep    : algo1(K 전체) / algo7(K<=5) 후보를 상위 K개 누적 배치 → K별 지표 (sync=true, 6Mbps)
  C) control  : algo7(K<=5), avoidBeaconSynchronization=false → "전송 시각이 겹치면 충돌이 생기는가" 대조군
  + 알고리즘 선정 시간(algo1 교차로 규칙 / algo7 greedy) 측정

실행 (VM, examples/veins 에서; veins_launchd가 켜져 있어야 함):
  python3 step2_sweep_all_metrics.py --quick            # 약 3분: 파이프라인 점검 (결과는 step2_quick/ 에 분리 저장)
  python3 step2_sweep_all_metrics.py --dry-run          # 실행 계획/예상 시간만 출력
  nohup python3 -u step2_sweep_all_metrics.py > step2_log.txt 2>&1 &     # 본 실행 (약 1시간)
  tail -f step2_log.txt

중단돼도 같은 명령을 다시 실행하면 이어서 한다 (이미 성공한 run은 건너뜀).
결과 (experiment_results/step2/):
  step2_runs_raw.csv         run 1개 = 1행 (모든 지표 + 시드 + 소요시간 + RSU 좌표)
  step2_isolated_summary.csv RSU(rank)별 단독 수신량
  step2_summary_by_K.csv     (phase, algo, sync, K)별 평균/표준편차 + η(간섭 손실률) + RSU별 최대 손실/이득
  step2_per_rsu_change.csv   RSU별 (다중 수신량 / 단독 수신량 − 1)
  step2_selection_time.csv   알고리즘 선정 시간
  step2_cost_summary.csv     알고리즘별 선정시간 + 평가 시뮬레이션 횟수/시간
  
η_K = 1 − Rx_K / Σ_{i≤K} Rx_isolated(i)   (≈0 이면 다중 RSU 간 간섭 손실 없음)
================================================================
"""
import argparse
import csv
import json
import os
import re
import signal
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from rsu_lib import sim_runner  # noqa: E402

TEMPLATE = "omnetpp_template.ini"
WORKING_INI = "omnetpp.ini"
CANDIDATES = {
    "algo1": "final_selected_rsus_algo1_corrected.csv",
    "algo7": "final_selected_rsus_corrected.csv",
}
OFFSET_X, OFFSET_Y = 644465.09, 5491786.25  # algo7_rsu_max_coverage.py 와 동일
SEED_BASE = 20261000  # repeat r 의 시드 = SEED_BASE + r (모든 K/phase에서 동일 → 짝지은 비교)
EST_SEC = {"isolated": 10, "sweep": 22, "control": 22}  # 관측 전 예상치
METRIC_COLS = ["PDR", "Total_Received", "Service_Ratio", "Jain_RSU", "Jain_Vehicle", "PER",
               "Collisions", "RXTX_Lost", "RSSI_Mean_dBm", "SNR_Mean_dB", "Channel_Busy", "Elapsed_Sec"]
EMPTY = sim_runner.empty_result()
META_COLS = ["Phase", "Algo", "Sync", "Bitrate", "K", "Rank_Iso", "Repeat", "Seed", "Success",
             "Elapsed_Sec", "Timestamp", "RSU_Coords", "Error"]
RAW_COLS = META_COLS + list(EMPTY.keys())

OUT_DIR = RAW_CSV = None  # main()에서 설정


def set_paths(quick):
    global OUT_DIR, RAW_CSV
    OUT_DIR = os.path.join("experiment_results", "step2_quick" if quick else "step2")
    RAW_CSV = os.path.join(OUT_DIR, "step2_runs_raw.csv")
    os.makedirs(OUT_DIR, exist_ok=True)


# ------------------------------------------------------------------ 계획
def load_cands(algo):
    df = pd.read_csv(CANDIDATES[algo], encoding="utf-8-sig").sort_values("Rank")
    return list(zip(df["Sim_X"].astype(float), df["Sim_Y"].astype(float)))


def make_job(phase, algo, sync, bitrate, k, rank, rep, coords):
    return {"phase": phase, "algo": algo, "sync": sync, "bitrate": bitrate, "k": k,
            "rank": rank, "rep": rep, "coords": coords, "seed": SEED_BASE + rep}


def job_key(j):
    return (j["phase"], j["algo"], str(j["sync"]), j["bitrate"], int(j["k"]),
            str(j["rank"]) if j["rank"] else "", int(j["rep"]))


def build_plan(a):
    phases = set(a.phases.split(","))
    ks = [int(x) for x in a.ks.split(",")]
    cks = [int(x) for x in a.control_ks.split(",")]
    cands = {n: load_cands(n) for n in CANDIDATES}
    # algo7은 K<=algo7_max_k 구간만 (단독 측정 / sweep / 대조군 모두 같은 범위)
    ks_by = {"algo1": ks, "algo7": [k for k in ks if k <= a.algo7_max_k]}
    cks7 = [k for k in cks if k <= a.algo7_max_k]
    for n, kk in (("algo1", ks), ("algo7", ks_by["algo7"] + cks7)):
        for k in kk:
            if k > len(cands[n]):
                raise SystemExit(f"K={k} > {n} 후보 수({len(cands[n])})")
    plan = []
    if "isolated" in phases:
        for rep in range(1, a.iso_repeats + 1):
            for algo, sync, maxk in (("algo7", True, max(ks_by["algo7"], default=0)),
                                     ("algo1", True, max(ks)),
                                     ("algo7", False, max(cks7, default=0))):
                if sync is False and "control" not in phases:
                    continue
                for r in range(1, maxk + 1):
                    plan.append(make_job("isolated", algo, sync, a.bitrate, 1, r, rep, [cands[algo][r - 1]]))
    if "sweep" in phases:
        for rep in range(1, a.repeats + 1):  # repeat가 바깥 루프 → 중간에 멈춰도 모든 K에 데이터가 있음
            for algo in ("algo1", "algo7"):
                for k in ks_by[algo]:
                    plan.append(make_job("sweep", algo, True, a.bitrate, k, None, rep, cands[algo][:k]))
    if "control" in phases:
        for rep in range(1, a.control_repeats + 1):
            for k in cks7:
                plan.append(make_job("control", "algo7", False, a.bitrate, k, None, rep, cands["algo7"][:k]))
    return plan


# ------------------------------------------------------------------ 실행
def make_template(bitrate, sync):
    """omnetpp_template.ini 는 건드리지 않고, bitrate/sync 만 바꾼 복사본을 OUT_DIR에 만든다."""
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        txt = f.read()
    txt, n1 = re.subn(r"^\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=.*$",
                      f"*.**.nic.mac1609_4.bitrate = {bitrate}  # [step2]", txt, flags=re.M)
    txt, n2 = re.subn(r"^\*\.rsu\[\*\]\.appl\.avoidBeaconSynchronization\s*=.*$",
                      f"*.rsu[*].appl.avoidBeaconSynchronization = {'true' if sync else 'false'}  # [step2]",
                      txt, flags=re.M)
    if n1 != 1 or n2 != 1:
        raise SystemExit(f"{TEMPLATE}에서 bitrate({n1}개)/avoidBeaconSynchronization({n2}개) 줄을 "
                         f"정확히 1개씩 찾지 못했어요. 템플릿 확인 필요.")
    path = os.path.join(OUT_DIR, f"_template_{bitrate}_sync{sync}.ini")
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def run_sim(timeout):
    t0 = time.time()
    p = subprocess.Popen([sim_runner.RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return False, time.time() - t0, "TIMEOUT " + (out or "")[-300:]
    out = out or ""
    ok = p.returncode == 0 and "<!> Error" not in out
    return ok, time.time() - t0, out


def run_job(job, templates, timeout):
    tpl = templates[(job["bitrate"], job["sync"])]
    err = ""
    for attempt in (1, 2):
        sim_runner.write_ini(tpl, WORKING_INI, job["coords"], job["k"], seed=job["seed"])
        sim_runner.reset_results_dir()
        ok, sec, out = run_sim(timeout)
        res = sim_runner.parse_all(job["coords"]) if ok else dict(EMPTY)
        if ok and res.get("Total_Generated", 0) == 0:
            ok, err = False, "BSM이 하나도 생성되지 않음"
        elif not ok:
            err = out[-300:]
        if ok:
            break
    row = {"Phase": job["phase"], "Algo": job["algo"], "Sync": job["sync"], "Bitrate": job["bitrate"],
           "K": job["k"], "Rank_Iso": job["rank"] or "", "Repeat": job["rep"], "Seed": job["seed"],
           "Success": ok, "Elapsed_Sec": round(sec, 2), "Timestamp": datetime.now().isoformat(timespec="seconds"),
           "RSU_Coords": json.dumps([[round(x, 2), round(y, 2)] for x, y in job["coords"]]),
           "Error": "" if ok else err.replace("\n", " | ")[:300]}
    row.update(res)
    return row


def append_row(row):
    new = not os.path.exists(RAW_CSV)
    with open(RAW_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RAW_COLS, extrasaction="ignore", restval="")
        if new:
            w.writeheader()
        w.writerow(row)


def load_done():
    done = set()
    if not os.path.exists(RAW_CSV):
        return done
    with open(RAW_CSV, "r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != RAW_COLS:
            raise SystemExit(f"{RAW_CSV} 의 컬럼이 현재 코드와 달라요. 파일 이름을 바꿔 두고 다시 실행하세요.")
        for r in rd:
            if r["Success"] == "True":
                done.add((r["Phase"], r["Algo"], r["Sync"], r["Bitrate"], int(r["K"]), r["Rank_Iso"], int(r["Repeat"])))
    return done


def preflight():
    for f in [TEMPLATE, "run"] + list(CANDIDATES.values()):
        if not os.path.exists(f):
            raise SystemExit(f"필요한 파일이 없어요: {f}")
    try:
        socket.create_connection(("localhost", 9999), timeout=2).close()
    except OSError:
        raise SystemExit("localhost:9999 에 연결이 안 돼요. veins_launchd 를 먼저 켜 주세요.")


# ------------------------------------------------------------------ 알고리즘 선정 시간
def measure_selection():
    rows = []

    def bench(name, fn, note, n=3):
        try:
            ts = []
            for _ in range(n):
                t = time.perf_counter()
                fn()
                ts.append(time.perf_counter() - t)
            rows.append({"Algo": name, "Selection_Sec": round(statistics.median(ts), 4),
                         "Selection_Sims": 0, "Note": note})
        except (Exception, SystemExit) as e:  # noqa: BLE001
            rows.append({"Algo": name, "Selection_Sec": float("nan"), "Selection_Sims": 0,
                         "Note": f"측정 실패: {type(e).__name__}: {e}"})

    def algo1():
        from algorithms.algo1_intersection.select_candidates import select_candidates
        select_candidates("erlangen.net.xml")

    def algo7():
        import algo7_rsu_max_coverage as m
        off = np.array([OFFSET_X, OFFSET_Y])
        pts = m.load_points_from_csv("vehicle_snapshots_2s.csv") - off
        cand = m.load_candidates_from_intersections("erlangen.net.xml") - off
        m.greedy_max_coverage(pts, cand, radius=150.0, k=27)

    bench("algo1", algo1, "교차로 차수/밀집도 규칙. net.xml 파싱 포함, 3회 중앙값, 시뮬레이션 0회")
    bench("algo7", algo7, "Greedy max coverage(r=150m, K=27). 스냅샷/교차로 로딩 포함, 3회 중앙값, 시뮬레이션 0회")
    path = os.path.join(OUT_DIR, "step2_selection_time.csv")
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    print(pd.DataFrame(rows).to_string(index=False))
    return path


# ------------------------------------------------------------------ 요약
def summarize():
    raw = pd.read_csv(RAW_CSV)
    raw = raw[raw["Success"].astype(str).str.lower() == "true"].copy()
    if raw.empty:
        print("성공한 run이 아직 없어요.")
        return
    raw["Sync"] = raw["Sync"].astype(str).str.lower() == "true"
    mcols = [c for c in METRIC_COLS if c in raw.columns]

    iso = raw[raw.Phase == "isolated"]
    iso_tab = pd.DataFrame()
    iso_rx = {}
    if not iso.empty:
        iso_tab = iso.groupby(["Algo", "Sync", "Bitrate", "Rank_Iso"], as_index=False).agg(
            N=("Total_Received", "size"), Iso_Rx=("Total_Received", "mean"), Iso_PDR=("PDR", "mean"),
            Iso_Service=("Service_Ratio", "mean"), Iso_RSSI=("RSSI_Mean_dBm", "mean"))
        iso_tab["Rank_Iso"] = iso_tab["Rank_Iso"].astype(int)
        iso_tab.to_csv(os.path.join(OUT_DIR, "step2_isolated_summary.csv"), index=False, encoding="utf-8-sig")
        iso_rx = {(r.Algo, bool(r.Sync), r.Bitrate, int(r.Rank_Iso)): r.Iso_Rx for r in iso_tab.itertuples()}

    multi = raw[raw.Phase.isin(["sweep", "control"])].copy()
    if multi.empty:
        print("sweep/control 결과가 아직 없어요.")
        return
    keys = ["Phase", "Algo", "Sync", "Bitrate", "K"]
    agg = {"N": ("Total_Received", "size")}
    for c in mcols:
        agg[c + "_mean"] = (c, "mean")
        agg[c + "_std"] = (c, "std")
    byk = multi.groupby(keys, as_index=False).agg(**agg)

    def iso_sum(r):
        s = 0.0
        for rk in range(1, int(r.K) + 1):
            v = iso_rx.get((r.Algo, bool(r.Sync), r.Bitrate, rk))
            if v is None:
                return np.nan
            s += v
        return s

    byk["Iso_Rx_Sum"] = byk.apply(iso_sum, axis=1)
    byk["Eta"] = 1 - byk["Total_Received_mean"] / byk["Iso_Rx_Sum"]

    rows = []
    for (phase, algo, sync, br, k), g in multi.groupby(keys):
        lists = []
        for _, r in g.iterrows():
            if str(r.get("PerRSU_Source")) != "position":
                continue
            try:
                lst = json.loads(r["PerRSU_Rx"])
            except (TypeError, ValueError):
                continue
            if len(lst) == int(k):
                lists.append(lst)
        if not lists:
            continue
        for i, mv in enumerate(np.mean(lists, axis=0)):
            iv = iso_rx.get((algo, bool(sync), br, i + 1))
            rows.append({"Phase": phase, "Algo": algo, "Sync": sync, "Bitrate": br, "K": int(k),
                         "Rank": i + 1, "Iso_Rx": iv, "Multi_Rx_mean": round(float(mv), 1),
                         "Rel_Change_pct": round((mv / iv - 1) * 100, 2) if iv else np.nan})
    per = pd.DataFrame(rows)
    if not per.empty:
        per.to_csv(os.path.join(OUT_DIR, "step2_per_rsu_change.csv"), index=False, encoding="utf-8-sig")
        ex = per.groupby(keys).agg(Max_RSU_Loss_pct=("Rel_Change_pct", lambda s: max(0.0, -s.min())),
                                   Max_RSU_Gain_pct=("Rel_Change_pct", lambda s: max(0.0, s.max()))).reset_index()
        byk = byk.merge(ex, on=keys, how="left")
    byk.to_csv(os.path.join(OUT_DIR, "step2_summary_by_K.csv"), index=False, encoding="utf-8-sig")

    sel_path = os.path.join(OUT_DIR, "step2_selection_time.csv")
    sel = pd.read_csv(sel_path) if os.path.exists(sel_path) else pd.DataFrame()
    cost = []
    for algo in ("algo1", "algo7"):
        s = multi[(multi.Phase == "sweep") & (multi.Algo == algo)]
        if s.empty:
            continue
        sel_sec = float(sel.loc[sel.Algo == algo, "Selection_Sec"].iloc[0]) if (not sel.empty and (sel.Algo == algo).any()) else np.nan
        tot = float(s.Elapsed_Sec.sum())
        cost.append({"Algo": algo, "Selection_Sec": sel_sec, "Selection_Sims": 0, "Eval_Sims": len(s),
                     "Eval_Sim_Sec_total": round(tot, 1), "Mean_Sec_per_Sim": round(float(s.Elapsed_Sec.mean()), 2),
                     "Total_Sec": round(tot + (0 if np.isnan(sel_sec) else sel_sec), 1)})
    if cost:
        pd.DataFrame(cost).to_csv(os.path.join(OUT_DIR, "step2_cost_summary.csv"), index=False, encoding="utf-8-sig")

    show = [c for c in ["Phase", "Algo", "Sync", "K", "N", "PDR_mean", "Total_Received_mean", "Service_Ratio_mean",
                        "Jain_RSU_mean", "PER_mean", "Collisions_mean", "RSSI_Mean_dBm_mean", "Eta",
                        "Max_RSU_Loss_pct", "Max_RSU_Gain_pct", "Elapsed_Sec_mean"] if c in byk.columns]
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.3f}".format):
        print("\n" + byk[show].to_string(index=False))
    print(f"\n저장 위치: {OUT_DIR}/")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="2단계: 전체 지표 K-sweep")
    ap.add_argument("--phases", default="isolated,sweep,control")
    ap.add_argument("--ks", default="1,2,3,4,5,8,10,15,20,27")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--iso-repeats", type=int, default=1)
    ap.add_argument("--control-ks", default="1,3,5,10,27")
    ap.add_argument("--control-repeats", type=int, default=3)
    ap.add_argument("--algo7-max-k", type=int, default=5, help="algo7은 K가 이 값 이하인 구간만 실행")
    ap.add_argument("--bitrate", default="6Mbps")
    ap.add_argument("--timeout", type=int, default=1800, help="run 1개당 제한(초)")
    ap.add_argument("--quick", action="store_true", help="K=1,3 / 반복 1회로 파이프라인 점검 (step2_quick/ 에 저장)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--redo-selection", action="store_true")
    a = ap.parse_args()
    if a.quick:
        a.ks, a.control_ks = "1,3", "1,3"
        a.repeats = a.iso_repeats = a.control_repeats = 1
    set_paths(a.quick)

    if a.summarize_only:
        summarize()
        return

    plan = build_plan(a)
    done = load_done()
    todo = [j for j in plan if job_key(j) not in done]
    counts = {p: sum(1 for j in todo if j["phase"] == p) for p in ("isolated", "sweep", "control")}
    est = sum(EST_SEC[j["phase"]] for j in todo) / 60
    print(f"총 {len(plan)} run 중 남은 것 {len(todo)} (isolated {counts['isolated']}, sweep {counts['sweep']}, "
          f"control {counts['control']}) · 예상 {est:.0f}분 · 결과 폴더 {OUT_DIR}/")
    if a.dry_run:
        return

    preflight()
    templates = {(j["bitrate"], j["sync"]): None for j in plan}
    for key in templates:
        templates[key] = make_template(*key)
    if "sweep" in a.phases and (a.redo_selection or not os.path.exists(os.path.join(OUT_DIR, "step2_selection_time.csv"))):
        print("\n[알고리즘 선정 시간 측정]")
        measure_selection()

    obs = {}  # phase -> 이번 세션에서 관측한 run 소요시간 목록
    t_start = time.time()
    checked = False
    try:
        for n, job in enumerate(todo, 1):
            row = run_job(job, templates, a.timeout)
            append_row(row)
            obs.setdefault(job["phase"], []).append(row["Elapsed_Sec"])
            if row["Success"] and not checked:
                checked = True
                if not row["Metrics_OK"]:
                    raise SystemExit("Metrics_OK=False: C++ 계측이 반영 안 된 빌드예요. make 후 다시 실행하세요.")
            rest = todo[n:]
            eta = sum((statistics.mean(obs[j["phase"]]) if obs.get(j["phase"]) else EST_SEC[j["phase"]])
                      for j in rest) / 60
            tag = f"{job['phase']}/{job['algo']}/sync={job['sync']} K={job['k']}" + \
                  (f" rank={job['rank']}" if job["rank"] else "") + f" rep={job['rep']}"
            if row["Success"]:
                print(f"[{n}/{len(todo)}] {tag}: PDR={row['PDR']}% Rx={row['Total_Received']} "
                      f"Svc={row['Service_Ratio']}% PER={row['PER']} Coll={row['Collisions']} "
                      f"({row['Elapsed_Sec']}s, 남은 약 {eta:.0f}분)", flush=True)
            else:
                print(f"[{n}/{len(todo)}] {tag}: !! 실패 {row['Error'][:120]}", flush=True)
    except KeyboardInterrupt:
        print("\n중단됨. 같은 명령으로 다시 실행하면 이어서 해요.")
    print(f"\n이번 세션 소요 {(time.time() - t_start) / 60:.1f}분")
    summarize()


if __name__ == "__main__":
    main()
