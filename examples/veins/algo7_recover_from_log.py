"""
algo7_recover_from_log.py
================================================================
중간에 죽은 nohup 실행의 로그 파일(run_log_corrected.txt)에서
완료된 반복 결과를 파싱해 CSV로 복구하는 스크립트
================================================================
"""

import argparse
import re

import pandas as pd

LINE_RE = re.compile(
    r"\[K=(\d+) / repeat (\d+)\] 총 발신: (\d+), 차량 대수: (\d+), "
    r"기대 수신: (\d+), 실제 수신: (\d+), PDR: ([\d.]+)%, 실측 소요시간: ([\d.]+)s"
)


def main():
    parser = argparse.ArgumentParser(description="중단된 nohup 로그에서 완료된 결과를 복구")
    parser.add_argument("--log", type=str, default="run_log_corrected.txt")
    parser.add_argument("--out", type=str, default="algo7_k_vs_pdr_multirun_raw_corrected_recovered.csv")
    args = parser.parse_args()

    with open(args.log, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    rows = []
    for m in LINE_RE.finditer(content):
        k, repeat, gen, nv, er, ar, pdr, el = m.groups()
        rows.append({
            "K": int(k), "Repeat": int(repeat), "Seed": -1,  # 로그에 시드가 안 찍혀서 -1(알수없음)
            "Total_Generated": int(gen), "Num_Vehicles": int(nv),
            "Expected_Received": int(er), "Actual_Received": int(ar),
            "PDR(%)": float(pdr), "Elapsed_Sec": float(el),
        })

    if not rows:
        print("!! 로그에서 완료된 반복을 하나도 못 찾았습니다. 로그 파일/형식을 확인하세요.")
        return

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")

    summary = df.groupby("K")["Repeat"].count().reset_index().rename(columns={"Repeat": "완료된 반복 수"})
    print("=" * 50)
    print(" K별 복구된 반복 횟수 (30이 안 되면 그 K는 이어서 더 필요)")
    print("=" * 50)
    print(summary.to_string(index=False))
    print("=" * 50)
    print(f"\n✔ 총 {len(df)}개 반복 결과를 '{args.out}' 로 복구했습니다.")

    incomplete = summary[summary["완료된 반복 수"] < 30]
    if len(incomplete):
        min_incomplete_k = int(incomplete["K"].min())
        print(f"\n-> K={min_incomplete_k}부터는 30회를 채우지 못했으니, "
              f"K={min_incomplete_k}부터 다시(또는 이어서) 돌려야 합니다.")


if __name__ == "__main__":
    main()
