# -*- coding: utf-8 -*-
"""
algo7_step0_dilution_check.py  (0단계 - 시뮬레이션 없이 기존 결과만으로 분석)
================================================================
가설 검증용: "K가 늘면 PDR이 떨어지는 건 충돌 때문인가, 지표 정의(희석) 때문인가?"

현재 PDR 정의:  PDR_K = Rx_K / (K * G * N)     (G=RSU 1대 발신량, N=차량 수)
RSU 간 간섭이 0이라면  Rx_K = sum_i Rx_iso(i)  이므로
   PDR_K(예측) = mean_i PDR_iso(i)      ← 단독 PDR의 단순 평균 (희석 모델)
간섭 손실률 (interference loss ratio):
   eta_K = 1 - Rx_K / sum_i Rx_iso(i) = 1 - K*PDR_K / sum_i PDR_iso(i)
   eta≈0  → 충돌/간섭으로 잃는 패킷 없음 (PDR 하락은 순전히 희석)
   eta>0  → 다중 RSU 간섭 손실 존재 (원래 가설 지지)

또한 "K가 늘 때 PDR이 오르는 시점"은 희석 모델상
   PDR_iso(K번째) > PDR_{K-1}  일 때 오르고, 아니면 내려간다 → 일치율을 계산.

입력(모두 기존 산출물), 출력:
   step0_dilution_table.csv, step0_dilution_summary.csv, step0_dilution.png, step0_marginal_eta_vs_distance.png
================================================================
"""
import os
import warnings
import logging
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.pyplot as plt

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# (라벨, 다중 RSU 결과, 단독 RSU 결과) - 같은 후보 리스트/같은 bitrate끼리만 짝지음
DATASETS = [
    ("algo1 · 6Mbps",
     ("raw", "experiment_results/multi/algo1/algo1_multi_raw.csv"),
     "algo7_isolated_rsu_trend_block4_algo1.csv",
     "final_selected_rsus_algo1_corrected.csv"),
    ("algo7 · 6Mbps",
     ("raw", "experiment_results/multi/algo7/algo7_multi_raw.csv"),
     "algo7_isolated_rsu_trend_block2_6M.csv",
     "final_selected_rsus_corrected.csv"),
    ("algo7 · 27Mbps",
     ("trend", "algo7_k_vs_pdr_trend_block1_27M.csv"),
     "algo7_isolated_rsu_trend_block1_27M.csv",
     "final_selected_rsus_corrected.csv"),
    ("algo7 · 27Mbps (legacy coords, 30 runs)",
     ("legacy", "algo7_k_pdr_received_table.csv"),
     None,
     None),  # 구 좌표계 후보 → 거리 분석 제외
]


def nearest_prev_dist(cand_csv, k):
    """K번째로 추가된 RSU와 이미 배치된 1..K-1번 RSU 사이 최소 거리(m)."""
    if cand_csv is None or k < 2 or not os.path.exists(cand_csv):
        return np.nan
    c = pd.read_csv(cand_csv, encoding="utf-8-sig").sort_values("Rank")
    xy = c[["Sim_X", "Sim_Y"]].to_numpy()
    if k > len(xy):
        return np.nan
    return float(np.min(np.hypot(*(xy[:k - 1] - xy[k - 1]).T)))


def load_multi(kind, path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    if kind == "raw":
        pdr_col = [c for c in df.columns if c.startswith("PDR")][0]
        g = df.groupby("K")
        out = pd.DataFrame({
            "PDR_K": g[pdr_col].mean(),
            "PDR_K_std": g[pdr_col].std(ddof=0),
            "Rx_K": g["Actual_Received"].mean(),
            "N_runs": g.size(),
        }).reset_index()
        return out, None
    if kind == "trend":
        return pd.DataFrame({"K": df["K"], "PDR_K": df["PDR_Mean"], "PDR_K_std": df["PDR_Std"],
                             "Rx_K": np.nan, "N_runs": df["N"]}), None
    # legacy: 한국어 컬럼 표 (단독 PDR 열 포함)
    cols = list(df.columns)
    out = pd.DataFrame({"K": df[cols[0]], "PDR_K": df[cols[1]], "PDR_K_std": df[cols[4]],
                        "Rx_K": df[cols[6]], "N_runs": df[cols[8]]})
    iso = pd.DataFrame({"Rank": df[cols[0]], "PDR_iso": df[cols[2]], "Rx_iso": np.nan})
    return out, iso


rows = []
for label, (kind, mpath), iso_path, cand_csv in DATASETS:
    if not os.path.exists(mpath):
        print(f"!! 건너뜀 (파일 없음): {mpath}")
        continue
    multi, iso = load_multi(kind, mpath)
    if iso is None:
        d = pd.read_csv(iso_path, encoding="utf-8-sig")
        iso = pd.DataFrame({"Rank": d["Rank"], "PDR_iso": d["PDR_Mean"], "Rx_iso": d["Received_Mean"]})
    iso = iso.sort_values("Rank").reset_index(drop=True)
    k1 = multi.loc[multi.K == 1, "PDR_K"]
    if len(k1) and abs(float(k1.iloc[0]) - iso.iloc[0]["PDR_iso"]) > 0.5:
        print(f"!! [{label}] 다중 K=1 PDR({float(k1.iloc[0]):.2f}) ≠ 단독 Rank1 PDR({iso.iloc[0]['PDR_iso']:.2f}) "
              f"→ 단독 실험 쪽 Rank1 값이 흔들림. 이 데이터셋의 eta에는 일정한 오프셋이 섞임")
    for _, r in multi.sort_values("K").iterrows():
        k = int(r["K"])
        top = iso.iloc[:k]
        sum_pdr_iso = top["PDR_iso"].sum()
        pred = sum_pdr_iso / k
        eta_pdr = 1 - (k * r["PDR_K"]) / sum_pdr_iso if sum_pdr_iso > 0 else np.nan
        sum_rx_iso = top["Rx_iso"].sum() if top["Rx_iso"].notna().all() else np.nan
        eta_rx = 1 - r["Rx_K"] / sum_rx_iso if (pd.notna(sum_rx_iso) and sum_rx_iso > 0) else np.nan
        rows.append({
            "Dataset": label, "K": k,
            "PDR_measured": round(r["PDR_K"], 3),
            "PDR_pred_mean_iso": round(pred, 3),
            "PDR_iso_added": round(iso.iloc[k - 1]["PDR_iso"], 3),
            "Rx_measured": r["Rx_K"], "Rx_sum_iso": sum_rx_iso,
            "eta_from_PDR": round(eta_pdr, 4),
            "eta_from_Rx": round(eta_rx, 4) if pd.notna(eta_rx) else np.nan,
            "N_runs": r["N_runs"],
            "added_RSU_nearest_dist_m": nearest_prev_dist(cand_csv, k),
        })

tab = pd.DataFrame(rows)
# 방향 일치: 실측 PDR이 오른 K에서, 희석모델도 "추가 RSU 단독PDR > 직전 PDR"을 예측했는가
tab["measured_up"] = tab.groupby("Dataset")["PDR_measured"].diff() > 0
prev = tab.groupby("Dataset")["PDR_measured"].shift(1)
tab["dilution_predicts_up"] = tab["PDR_iso_added"] > prev
tab[["measured_up", "dilution_predicts_up"]] = tab[["measured_up", "dilution_predicts_up"]].astype(object)
tab.loc[prev.isna(), ["measured_up", "dilution_predicts_up"]] = np.nan
# 한계 간섭 손실: K번째 RSU를 추가해서 실제로 늘어난 수신량이, 그 RSU 단독 수신량 대비 얼마나 모자란가
tab["Rx_iso_added"] = tab.groupby("Dataset")["Rx_sum_iso"].diff()
tab.loc[tab.K == 1, "Rx_iso_added"] = tab.loc[tab.K == 1, "Rx_sum_iso"]
tab["marginal_eta"] = 1 - tab.groupby("Dataset")["Rx_measured"].diff() / tab["Rx_iso_added"]
tab.loc[(tab.K == 1) | (tab.Rx_iso_added < 2000), "marginal_eta"] = np.nan  # 단독 수신이 너무 작으면 비율이 불안정
tab.to_csv("step0_dilution_table.csv", index=False, encoding="utf-8-sig")

summ = []
for label, g in tab.groupby("Dataset", sort=False):
    g2 = g.dropna(subset=["measured_up"])
    agree = (g2["measured_up"] == g2["dilution_predicts_up"]).mean() if len(g2) else np.nan
    err = (g["PDR_measured"] - g["PDR_pred_mean_iso"]).abs()
    summ.append({
        "Dataset": label, "K_range": f"{g.K.min()}–{g.K.max()}",
        "MAE_PDR_vs_dilution(%p)": round(err.mean(), 3),
        "max_abs_err(%p)": round(err.max(), 3),
        "eta_mean": round(g["eta_from_PDR"].mean(), 4),
        "eta_max": round(g["eta_from_PDR"].max(), 4),
        "up/down_direction_agreement": round(agree, 3),
        "num_K_where_PDR_rose": int(g2["measured_up"].sum()),
    })
summ = pd.DataFrame(summ)
summ.to_csv("step0_dilution_summary.csv", index=False, encoding="utf-8-sig")
print(summ.to_string(index=False))

# ---------------- 그림: 데이터셋별 small multiples (위: 실측 vs 희석예측, 아래: eta) -------------
plt.rcParams["axes.unicode_minus"] = False
BLUE, INK, MUTED, GRID = "#2a78d6", "#0b0b0b", "#52514e", "#e6e5e0"
labels = list(dict.fromkeys(tab["Dataset"]))
fig, axes = plt.subplots(2, len(labels), figsize=(4.2 * len(labels), 6.4),
                         gridspec_kw={"height_ratios": [3, 1.3]}, squeeze=False)
for j, label in enumerate(labels):
    g = tab[tab.Dataset == label]
    ax = axes[0][j]
    ax.plot(g.K, g.PDR_pred_mean_iso, color=MUTED, lw=2, ls="--", label="Dilution model (mean of isolated PDRs)")
    ax.plot(g.K, g.PDR_measured, color=BLUE, lw=2, marker="o", ms=5, label="Measured multi-RSU PDR")
    ax.set_title(label, fontsize=11, color=INK)
    ax.set_ylabel("PDR (%)" if j == 0 else "")
    ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if j == 0:
        ax.legend(frameon=False, fontsize=9)
    bx = axes[1][j]
    bx.bar(g.K, g.eta_from_PDR * 100, color=BLUE, width=0.7)
    bx.axhline(0, color=MUTED, lw=0.8)
    bx.set_ylabel("Interference loss η (%)" if j == 0 else "")
    bx.set_xlabel("K (number of RSUs)")
    bx.grid(axis="y", color=GRID, lw=0.8); bx.set_axisbelow(True)
    for s in ("top", "right"):
        bx.spines[s].set_visible(False)
fig.suptitle("Is multi-RSU PDR just the mean of isolated PDRs?  (η ≈ 0 → no interference loss)", fontsize=12, color=INK)
fig.tight_layout()
fig.savefig("step0_dilution.png", dpi=200)
# ---------------- 그림 2: 추가 RSU의 최근접 거리 vs 한계 간섭 손실 ----------------
sc = tab.dropna(subset=["marginal_eta", "added_RSU_nearest_dist_m"])
if len(sc):
    fig2, ax = plt.subplots(figsize=(6.4, 4.4))
    markers = ["o", "s", "^", "D"]
    for m, (label, g) in zip(markers, sc.groupby("Dataset", sort=False)):
        ax.scatter(g.added_RSU_nearest_dist_m, g.marginal_eta * 100, s=46, marker=m,
                   facecolor="none" if m != "o" else BLUE, edgecolor=BLUE, lw=1.5, label=label)
        for _, r in g[g.marginal_eta > 0.15].iterrows():
            ax.annotate(f"K={int(r.K)}", (r.added_RSU_nearest_dist_m, r.marginal_eta * 100),
                        xytext=(5, 3), textcoords="offset points", fontsize=8, color=MUTED)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Distance from added RSU to nearest existing RSU (m)")
    ax.set_ylabel("Marginal interference loss of added RSU (%)")
    ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.legend(frameon=False, fontsize=9)
    fig2.tight_layout(); fig2.savefig("step0_marginal_eta_vs_distance.png", dpi=200)
    try:
        from scipy.stats import spearmanr
        rho, p = spearmanr(sc.added_RSU_nearest_dist_m, sc.marginal_eta)
    except ImportError:  # scipy 없으면 rho만
        rho, p = sc.added_RSU_nearest_dist_m.rank().corr(sc.marginal_eta.rank()), float("nan")
    print(f"\n[거리 vs 한계 간섭손실] n={len(sc)}, Spearman rho={rho:.3f}, p={p:.4f}")
    print(sc[["Dataset", "K", "added_RSU_nearest_dist_m", "Rx_iso_added", "marginal_eta"]]
          .sort_values("marginal_eta", ascending=False).head(8).to_string(index=False))

print("저장: step0_dilution_table.csv, step0_dilution_summary.csv, step0_dilution.png")
