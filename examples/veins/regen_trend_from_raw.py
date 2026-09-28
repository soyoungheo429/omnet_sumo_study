"""
regen_trend_from_raw.py
================================================================
algo7_evaluate_k_pdr.py가 중간에 강제 종료(kill)됐을 때 쓰는 복구 스크립트.

algo7_evaluate_k_pdr.py는 반복(repeat)마다 raw CSV에 즉시 한 줄씩 append하지만
(algo7_evaluate_k_pdr.py:202-208), K별 평균/표준편차 요약(trend CSV)과 에러바
차트는 전체 루프가 다 끝난 뒤 마지막에만 생성한다(algo7_evaluate_k_pdr.py:541-592).
중간에 kill하면 이 두 개가 안 만들어지므로, 이미 저장된 raw CSV만 가지고
summary/plot 부분만 떼어내 재실행한다.

사용법:
    python3 regen_trend_from_raw.py \
        --raw-csv experiment_results/multi/algo1/algo1_multi_raw.csv \
        --trend-out experiment_results/multi/algo1/algo1_multi_trend.csv \
        --plot-out experiment_results/multi/algo1/algo1_multi_errorbar.png \
        --max-k 17
"""

import argparse
import pandas as pd
import matplotlib.pyplot as plt


def plot_errorbar_chart(summary_df: pd.DataFrame, out_path: str) -> None:
    plt.rcParams["axes.unicode_minus"] = False

    ks = summary_df["K"].values
    means = summary_df["PDR_Mean"].values
    stds = summary_df["PDR_Std"].values

    plt.figure(figsize=(9, 6))
    plt.errorbar(
        ks,
        means,
        yerr=stds,
        fmt="o-",
        color="royalblue",
        ecolor="lightcoral",
        elinewidth=2.5,
        capsize=8,
        markersize=9,
        label="Mean PDR +/- Std Dev",
    )

    for x, y in zip(ks, means):
        plt.text(
            x,
            y + (max(means) * 0.03 if len(means) else 1),
            f"{y:.2f}%",
            ha="center",
            color="blue",
            fontweight="bold",
            fontsize=10,
        )

    plt.xticks(ks)
    plt.xlabel("K (Number of Deployed RSUs)", fontsize=13)
    plt.ylabel("Packet Delivery Ratio (PDR) [%]", fontsize=13)
    plt.title(
        f"PDR vs. K (Number of RSUs) - Mean +/- Std Dev over {int(summary_df['N'].max())} runs",
        fontsize=14,
        pad=20,
    )
    plt.ylim(0, max(means + stds) * 1.25 if len(means) else 100)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="best")
    plt.tight_layout()

    plt.savefig(out_path, dpi=300)
    print(f"Saved error bar chart to '{out_path}'.")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="algo7_evaluate_k_pdr.py가 중간에 kill됐을 때, 이미 저장된 raw CSV로 "
        "trend CSV + errorbar PNG만 재생성한다."
    )
    parser.add_argument(
        "--raw-csv", required=True, help="algo7_evaluate_k_pdr.py가 남긴 raw CSV 경로"
    )
    parser.add_argument(
        "--trend-out", required=True, help="생성할 trend(요약) CSV 경로"
    )
    parser.add_argument("--plot-out", required=True, help="생성할 errorbar PNG 경로")
    parser.add_argument(
        "--max-k",
        type=int,
        default=None,
        help="이 값을 초과하는 K는 버린다 (중단 시점에 미완료였던 K 제외용)",
    )
    args = parser.parse_args()

    raw_df = pd.read_csv(args.raw_csv)

    if args.max_k is not None:
        before = raw_df["K"].max()
        raw_df = raw_df[raw_df["K"] <= args.max_k]
        print(
            f"K<= {args.max_k} 만 사용 (raw CSV에는 K={before}까지 있었음, "
            f"미완료 K={args.max_k + 1}~{before}는 제외)"
        )

    # K별로 --repeats 회 전부 채워지지 않은(=중단으로 일부만 기록된) K도 걸러낸다.
    counts = raw_df.groupby("K").size()
    full_repeats = counts.max()
    incomplete_ks = counts[counts < full_repeats].index.tolist()
    if incomplete_ks:
        print(
            f"반복 횟수가 부족한(중단으로 일부만 기록된) K 제외: {incomplete_ks} "
            f"(정상 K는 {full_repeats}회씩 있음)"
        )
        raw_df = raw_df[~raw_df["K"].isin(incomplete_ks)]

    summary_df = (
        raw_df.groupby("K")["PDR(%)"]
        .agg(PDR_Mean="mean", PDR_Std="std", PDR_Min="min", PDR_Max="max", N="count")
        .reset_index()
    )
    summary_df["PDR_Std"] = summary_df["PDR_Std"].fillna(0.0)

    elapsed_summary = raw_df.groupby("K")["Elapsed_Sec"].mean().reset_index()
    elapsed_summary = elapsed_summary.rename(
        columns={"Elapsed_Sec": "Elapsed_Sec_Mean"}
    )
    summary_df = summary_df.merge(elapsed_summary, on="K", how="left")

    summary_df = summary_df.round(2)
    if "Bitrate" in raw_df.columns:
        summary_df["Bitrate"] = raw_df["Bitrate"].iloc[0]
    if "AvoidBeaconSync" in raw_df.columns:
        summary_df["AvoidBeaconSync"] = raw_df["AvoidBeaconSync"].iloc[0]

    print(summary_df.to_string(index=False))

    summary_df.to_csv(args.trend_out, index=False, encoding="utf-8-sig")
    print(f"\n✔ trend CSV 저장: '{args.trend_out}'")

    plot_errorbar_chart(summary_df, args.plot_out)


if __name__ == "__main__":
    main()
