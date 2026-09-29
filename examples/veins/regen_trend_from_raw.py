import argparse
import pandas as pd
import matplotlib.pyplot as plt


def plot_errorbar_chart(summary_df, out_path):
    plt.rcParams["axes.unicode_minus"] = False

    ks = summary_df["K"].values
    means = summary_df["PDR_Mean"].values
    stds = summary_df["PDR_Std"].values

    plt.figure(figsize=(9, 6))
    plt.errorbar(
        ks, means, yerr=stds, fmt="o-", color="royalblue",
        ecolor="lightcoral", elinewidth=2.5, capsize=8,
        markersize=9, label="Mean PDR +/- Std Dev",
    )

    for x, y in zip(ks, means):
        plt.text(
            x, y + (max(means) * 0.03 if len(means) else 1),
            f"{y:.2f}%", ha="center", color="blue", fontweight="bold", fontsize=10,
        )

    plt.xticks(ks)
    plt.xlabel("K (Number of Deployed RSUs)", fontsize=13)
    plt.ylabel("Packet Delivery Ratio (PDR) [%]", fontsize=13)
    plt.title(
        f"PDR vs. K (Number of RSUs) - Mean +/- Std Dev over {int(summary_df['N'].max())} runs",
        fontsize=14, pad=20,
    )
    plt.ylim(0, max(means + stds) * 1.25 if len(means) else 100)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="best")
    plt.tight_layout()

    plt.savefig(out_path, dpi=300)
    print(f"Saved error bar chart to '{out_path}'.")
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-csv", required=True)
    parser.add_argument("--trend-out", required=True)
    parser.add_argument("--plot-out", required=True)
    parser.add_argument("--max-k", type=int, default=None)
    args = parser.parse_args()

    raw_df = pd.read_csv(args.raw_csv)

    if args.max_k is not None:
        before = raw_df["K"].max()
        raw_df = raw_df[raw_df["K"] <= args.max_k]
        print(f"K<= {args.max_k} 만 사용 (raw CSV에는 K={before}까지 있었음)")

    counts = raw_df.groupby("K").size()
    full_repeats = counts.max()
    incomplete_ks = counts[counts < full_repeats].index.tolist()
    if incomplete_ks:
        print(f"반복 횟수가 부족한 K 제외: {incomplete_ks}")
        raw_df = raw_df[~raw_df["K"].isin(incomplete_ks)]

    summary_df = (
        raw_df.groupby("K")["PDR(%)"]
        .agg(PDR_Mean="mean", PDR_Std="std", PDR_Min="min", PDR_Max="max", N="count")
        .reset_index()
    )
    summary_df["PDR_Std"] = summary_df["PDR_Std"].fillna(0.0)

    elapsed_summary = raw_df.groupby("K")["Elapsed_Sec"].mean().reset_index()
    elapsed_summary = elapsed_summary.rename(columns={"Elapsed_Sec": "Elapsed_Sec_Mean"})
    summary_df = summary_df.merge(elapsed_summary, on="K", how="left")

    summary_df = summary_df.round(2)
    if "Bitrate" in raw_df.columns:
        summary_df["Bitrate"] = raw_df["Bitrate"].iloc[0]
    if "AvoidBeaconSync" in raw_df.columns:
        summary_df["AvoidBeaconSync"] = raw_df["AvoidBeaconSync"].iloc[0]

    print(summary_df.to_string(index=False))

    summary_df.to_csv(args.trend_out, index=False, encoding="utf-8-sig")
    print(f"trend CSV 저장: '{args.trend_out}'")

    plot_errorbar_chart(summary_df, args.plot_out)


if __name__ == "__main__":
    main()
