# -*- coding: utf-8 -*-
"""
step1_smoke_test.py  — C++ [metrics] 재빌드 후 지표가 제대로 찍히는지 1회씩 확인
실행:  cd ~/veins/examples/veins && python3 step1_smoke_test.py
       (옵션) --csv final_selected_rsus_corrected.csv --ks 1,3
확인 포인트:
  - Metrics_OK=True            → 재빌드가 반영됨 (False면 make 다시)
  - PerRSU_Source=position     → RSU 좌표 매칭 성공 (mac이면 Jain은 맞지만 RSU 순서 매칭은 불가)
  - K=1의 PDR이 기존 결과와 같음 → 기존 지표 회귀 없음
  - RSSI_Mean_dBm 이 대략 -60 ~ -89 dBm (minPowerLevel = -89dBm)
"""
import argparse
import json
import os
import sys

import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
from rsu_lib import sim_runner  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="final_selected_rsus_corrected.csv")
ap.add_argument("--ks", default="1,3")
ap.add_argument("--seed", type=int, default=12345)
args = ap.parse_args()

df = pd.read_csv(args.csv, encoding="utf-8-sig").sort_values("Rank")
rows = []
for k in [int(x) for x in args.ks.split(",")]:
    coords = list(zip(df["Sim_X"].head(k), df["Sim_Y"].head(k)))
    sim_runner.write_ini("omnetpp_template.ini", "omnetpp.ini", coords, k, seed=args.seed)
    sim_runner.reset_results_dir()
    ok, sec, out = sim_runner.run_simulation(verbose=False)
    if not ok:
        print(f"!! K={k} 시뮬레이션 실패. 마지막 출력:\n" + out[-2000:])
        continue
    r = sim_runner.parse_all(coords)
    r.update(K=k, Elapsed_Sec=round(sec, 1))
    rows.append(r)
    print(f"\n=== K={k} ({sec:.1f}s) ===")
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))

if rows:
    pd.DataFrame(rows).to_csv("step1_smoke_test_result.csv", index=False, encoding="utf-8-sig")
    bad = [r["K"] for r in rows if not r["Metrics_OK"]]
    print("\n저장: step1_smoke_test_result.csv")
    print("!! Metrics_OK=False → C++ 재빌드가 반영 안 됨: K=" + str(bad) if bad else "계측 정상 ✓")
