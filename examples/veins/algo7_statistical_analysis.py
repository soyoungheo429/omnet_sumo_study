"""
algo7_statistical_analysis.py
================================================================
4단계: K(RSU 대수)별 PDR 통계 검정 (정규성 -> ANOVA/Kruskal-Wallis -> 사후검정)
================================================================

배경:
  - algo7_evaluate_k_pdr.py로 얻은 algo7_k_vs_pdr_multirun_raw.csv(K=1~27,
    각 30회 반복, 총 810행)를 입력으로 받아, K값에 따른 PDR 차이가 통계적으로
    유의한지 검증한다.

동작 순서:
  1) K별로 Shapiro-Wilk 정규성 검정 (alpha=0.05)
  2) 모든 K 그룹이 정규분포를 만족하면 One-way ANOVA, 하나라도 위배하면
     Kruskal-Wallis 검정 사용 (원 계획서 그대로)
  3) 유의하면(p<0.05) 사후검정 실행:
     - ANOVA였다면 Tukey HSD
     - Kruskal-Wallis였다면 Dunn's test (scikit-posthocs 있으면 사용,
       없으면 Bonferroni 보정을 적용한 pairwise Mann-Whitney U로 대체)
  4) K별 평균 + 95% 신뢰구간(t분포 기준) 표와 막대/선 그래프 저장
"""

import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

DEFAULT_RAW_CSV = "algo7_k_vs_pdr_multirun_raw.csv"
ALPHA = 0.05

OUTPUT_NORMALITY_CSV = "algo7_stats_normality.csv"
OUTPUT_SUMMARY_CSV = "algo7_stats_summary_ci.csv"
OUTPUT_OMNIBUS_TXT = "algo7_stats_omnibus_result.txt"
OUTPUT_POSTHOC_CSV = "algo7_stats_posthoc.csv"
OUTPUT_CI_PLOT_PNG = "algo7_stats_mean_ci_barplot.png"


def mean_ci(values: np.ndarray, confidence: float = 0.95):
    """t분포 기준 평균과 신뢰구간(하한, 상한)을 계산."""
    n = len(values)
    m = np.mean(values)
    se = stats.sem(values)
    if n > 1 and se > 0:
        h = se * stats.t.ppf((1 + confidence) / 2.0, n - 1)
    else:
        h = 0.0
    return m, m - h, m + h


def main():
    parser = argparse.ArgumentParser(description="K별 PDR 통계 검정 (정규성->ANOVA/KW->사후검정)")
    parser.add_argument("--raw-csv", type=str, default=DEFAULT_RAW_CSV)
    parser.add_argument("--normality-out", type=str, default=OUTPUT_NORMALITY_CSV)
    parser.add_argument("--summary-out", type=str, default=OUTPUT_SUMMARY_CSV)
    parser.add_argument("--omnibus-out", type=str, default=OUTPUT_OMNIBUS_TXT)
    parser.add_argument("--posthoc-out", type=str, default=OUTPUT_POSTHOC_CSV)
    parser.add_argument("--ci-plot-out", type=str, default=OUTPUT_CI_PLOT_PNG)
    args = parser.parse_args()

    df = pd.read_csv(args.raw_csv)
    pdr_col = "PDR(%)"
    ks = sorted(df["K"].unique())
    groups = {k: df.loc[df["K"] == k, pdr_col].values for k in ks}

    # ---------------------------------------------------------------
    # 1) K별 정규성 검정 (Shapiro-Wilk)
    # ---------------------------------------------------------------
    normality_rows = []
    all_normal = True
    for k in ks:
        vals = groups[k]
        if len(vals) < 3 or np.allclose(vals, vals[0]):
            # 표본이 너무 적거나 전부 동일한 값이면 Shapiro 자체가 정의되지 않음 -> 정규성 위배로 처리
            stat, p = float("nan"), 0.0
        else:
            stat, p = stats.shapiro(vals)
        is_normal = p >= ALPHA
        if not is_normal:
            all_normal = False
        normality_rows.append({"K": k, "N": len(vals), "Shapiro_W": stat, "p_value": p, "Normal(p>=0.05)": is_normal})

    normality_df = pd.DataFrame(normality_rows)
    normality_df.to_csv(args.normality_out, index=False, encoding="utf-8-sig")

    print("=" * 70)
    print(" 1) K별 정규성 검정 (Shapiro-Wilk, alpha=0.05)")
    print("=" * 70)
    print(normality_df.to_string(index=False))
    n_fail = (~normality_df["Normal(p>=0.05)"]).sum()
    print(f"\n-> {n_fail}/{len(ks)}개 K 그룹이 정규성을 만족하지 않음.")

    # ---------------------------------------------------------------
    # 2) 전체 K 그룹 정규성 결과에 따라 ANOVA 또는 Kruskal-Wallis 선택
    # ---------------------------------------------------------------
    group_values = [groups[k] for k in ks]

    if all_normal:
        test_name = "One-way ANOVA"
        stat_val, p_val = stats.f_oneway(*group_values)
    else:
        test_name = "Kruskal-Wallis"
        stat_val, p_val = stats.kruskal(*group_values)

    is_significant = p_val < ALPHA

    omnibus_summary = (
        f"사용한 검정: {test_name}\n"
        f"통계량: {stat_val:.4f}\n"
        f"p-value: {p_val:.6g}\n"
        f"유의성(alpha=0.05): {'유의함 (K에 따라 PDR이 유의하게 다름)' if is_significant else '유의하지 않음'}\n"
    )
    with open(args.omnibus_out, "w", encoding="utf-8") as f:
        f.write(omnibus_summary)

    print("\n" + "=" * 70)
    print(" 2) 전체 K군 비교 (Omnibus Test)")
    print("=" * 70)
    print(omnibus_summary)

    # ---------------------------------------------------------------
    # 3) 유의하면 사후검정 (ANOVA->Tukey HSD / KW->Dunn 또는 Bonferroni pairwise MWU)
    # ---------------------------------------------------------------
    posthoc_df = None
    if is_significant:
        print("=" * 70)
        print(" 3) 사후검정 (Post-hoc)")
        print("=" * 70)

        if all_normal:
            try:
                from statsmodels.stats.multicomp import pairwise_tukeyhsd
                tukey = pairwise_tukeyhsd(df[pdr_col], df["K"], alpha=ALPHA)
                posthoc_df = pd.DataFrame(data=tukey._results_table.data[1:], columns=tukey._results_table.data[0])
                posthoc_df.to_csv(args.posthoc_out, index=False, encoding="utf-8-sig")
                print(posthoc_df.to_string(index=False))
            except ImportError:
                print("!! statsmodels 미설치 -> Bonferroni 보정 pairwise t-test로 대체합니다.")
                pairs = []
                n_pairs = len(ks) * (len(ks) - 1) // 2
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        k1, k2 = ks[i], ks[j]
                        t_stat, t_p = stats.ttest_ind(groups[k1], groups[k2])
                        p_adj = min(t_p * n_pairs, 1.0)
                        pairs.append({
                            "K1": k1, "K2": k2, "t_stat": t_stat,
                            "p_raw": t_p, "p_bonferroni": p_adj,
                            "Significant(p_adj<0.05)": p_adj < ALPHA,
                        })
                posthoc_df = pd.DataFrame(pairs)
                posthoc_df.to_csv(args.posthoc_out, index=False, encoding="utf-8-sig")
                sig_pairs = posthoc_df[posthoc_df["Significant(p_adj<0.05)"]]
                print(f"총 {n_pairs}개 쌍 중 {len(sig_pairs)}개 쌍이 유의함 (p_bonferroni<0.05).")
                print(sig_pairs.to_string(index=False))
        else:
            try:
                import scikit_posthocs as sp
                dunn = sp.posthoc_dunn(df, val_col=pdr_col, group_col="K", p_adjust="bonferroni")
                dunn.to_csv(args.posthoc_out, encoding="utf-8-sig")
                print("Dunn's test (Bonferroni 보정) p-value 행렬:")
                print(dunn.to_string())
                posthoc_df = dunn
            except ImportError:
                print("!! scikit-posthocs 미설치 -> Bonferroni 보정 pairwise Mann-Whitney U로 대체합니다.")
                pairs = []
                n_pairs = len(ks) * (len(ks) - 1) // 2
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        k1, k2 = ks[i], ks[j]
                        u_stat, u_p = stats.mannwhitneyu(groups[k1], groups[k2], alternative="two-sided")
                        p_adj = min(u_p * n_pairs, 1.0)  # Bonferroni 보정
                        pairs.append({
                            "K1": k1, "K2": k2, "U_stat": u_stat,
                            "p_raw": u_p, "p_bonferroni": p_adj,
                            "Significant(p_adj<0.05)": p_adj < ALPHA,
                        })
                posthoc_df = pd.DataFrame(pairs)
                posthoc_df.to_csv(args.posthoc_out, index=False, encoding="utf-8-sig")
                sig_pairs = posthoc_df[posthoc_df["Significant(p_adj<0.05)"]]
                print(f"총 {n_pairs}개 쌍 중 {len(sig_pairs)}개 쌍이 유의함 (p_bonferroni<0.05).")
                print(sig_pairs.to_string(index=False))
    else:
        print("\n(전체 검정이 유의하지 않아 사후검정은 생략합니다.)")

    # ---------------------------------------------------------------
    # 4) K별 평균 + 95% 신뢰구간 표 및 그래프
    # ---------------------------------------------------------------
    summary_rows = []
    for k in ks:
        vals = groups[k]
        m, lo, hi = mean_ci(vals)
        summary_rows.append({
            "K": k, "N": len(vals), "Mean_PDR": round(m, 4),
            "CI95_Lower": round(lo, 4), "CI95_Upper": round(hi, 4),
            "Std": round(np.std(vals, ddof=1), 4),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(args.summary_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(" 4) K별 평균 PDR + 95% 신뢰구간")
    print("=" * 70)
    print(summary_df.to_string(index=False))

    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(13, 6))
    means = summary_df["Mean_PDR"].values
    err_lower = means - summary_df["CI95_Lower"].values
    err_upper = summary_df["CI95_Upper"].values - means
    plt.bar(summary_df["K"], means, yerr=[err_lower, err_upper], capsize=4,
            color='cornflowerblue', ecolor='firebrick', alpha=0.85)
    plt.xlabel("K (Number of Deployed RSUs)", fontsize=13)
    plt.ylabel("Mean PDR (%) with 95% CI", fontsize=13)
    plt.title(f"Mean PDR by K with 95% CI ({test_name}, p={p_val:.4g})", fontsize=14, pad=20)
    plt.xticks(summary_df["K"])
    plt.grid(True, axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(args.ci_plot_out, dpi=300)
    print(f"\nSaved mean+95%CI bar chart to '{args.ci_plot_out}'.")
    plt.close()


if __name__ == "__main__":
    main()
