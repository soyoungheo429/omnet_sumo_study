#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step3a_ga_generations_viz.py  (시뮬레이션 0번, 몇 초)
================================================================
GA가 세대마다 어디를 탐색했는지 시각화한다. 입력은 기존 GA 결과 CSV (Gen, Sim_X, Sim_Y, PDR ...).
  step3a_ga_generations_map.png   (왼쪽: 전체 지도 / 가운데: 최종 최적점 확대 / 오른쪽: 세대별 PDR)
  step3a_ga_generations_map.html  (folium 이 설치돼 있을 때만, 세대별 색 + 팝업)
  step3a_per_generation_coords.csv (세대별 최고/평균 PDR, 최고 개체 좌표, 개체 흩어짐 정도)

실행:  python3 step3a_ga_generations_viz.py [--csv <GA 결과 CSV>]
================================================================
"""
import argparse
import os
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

DEFAULT_CSV = os.path.join("experiment_results", "single", "algo4", "algo4_GA_hybrid_corrected",
                           "ga_hybrid_final_results_corrected.csv")
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def gen_colors(gens):
    cmap = plt.get_cmap("Blues")  # 순서가 있는 값(세대) → 단일 색상 명도 램프
    lo, hi = min(gens), max(gens)
    return {g: cmap(0.25 + 0.75 * (g - lo) / max(hi - lo, 1)) for g in gens}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--out", default=os.path.join("experiment_results", "step3"))
    ap.add_argument("--zoom", type=float, default=250.0, help="확대 패널 반경(m)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    d = pd.read_csv(a.csv, encoding="utf-8-sig")
    gens = sorted(d.Gen.unique())
    col = gen_colors(gens)
    best = d.loc[d.PDR.idxmax()]

    # 세대별 요약
    rows = []
    for g, s in d.groupby("Gen"):
        top = s.loc[s.PDR.idxmax()]
        c = s[["Sim_X", "Sim_Y"]].mean().to_numpy()
        spread = float(np.mean(np.hypot(s.Sim_X - c[0], s.Sim_Y - c[1])))
        rows.append({"Gen": g, "N": len(s), "PDR_max": round(s.PDR.max(), 2), "PDR_mean": round(s.PDR.mean(), 2),
                     "Best_Sim_X": round(top.Sim_X, 1), "Best_Sim_Y": round(top.Sim_Y, 1),
                     "Spread_m": round(spread, 1)})
    gs = pd.DataFrame(rows)
    gs.to_csv(os.path.join(a.out, "step3a_per_generation_coords.csv"), index=False, encoding="utf-8-sig")
    print(gs.to_string(index=False))

    fig, axes = plt.subplots(1, 3, figsize=(17, 5.6), gridspec_kw={"width_ratios": [1.0, 1.0, 0.9]})
    # ---- (1) 전체 지도
    ax = axes[0]
    for g in gens:
        s = d[d.Gen == g]
        ax.scatter(s.Sim_X, s.Sim_Y, s=26, color=col[g], edgecolor="white", linewidth=0.6, zorder=3, label=f"Gen {g}")
    path = gs[["Best_Sim_X", "Best_Sim_Y"]].to_numpy()
    ax.plot(path[:, 0], path[:, 1], color=MUTED, lw=1, zorder=2)
    ax.scatter([best.Sim_X], [best.Sim_Y], marker="*", s=240, color="#eb6834", edgecolor=INK, linewidth=0.8, zorder=5)
    ax.set_xlim(0, sim_eval.WIDTH + 50)
    ax.set_ylim(sim_eval.HEIGHT + 50, 0)  # y 아래로 증가 = 지도의 북쪽이 위
    ax.set_aspect("equal")
    ax.set_title("All individuals by generation (north up)", fontsize=11, color=INK, loc="left")
    ax.set_xlabel("Sim X (m)")
    ax.set_ylabel("Sim Y (m)")
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="lower right", title="darker = later", title_fontsize=7)
    # ---- (2) 확대
    ax = axes[1]
    z = a.zoom
    for g in gens:
        s = d[d.Gen == g]
        ax.scatter(s.Sim_X, s.Sim_Y, s=44, color=col[g], edgecolor="white", linewidth=0.7, zorder=3)
    # 같은 좌표가 연속으로 최고였던 세대는 "4-8" 처럼 묶어서 라벨 (겹침 방지)
    groups, cur = [], None
    for _, r in gs.iterrows():
        key = (r.Best_Sim_X, r.Best_Sim_Y)
        if cur and cur["key"] == key:
            cur["hi"] = int(r.Gen)
        else:
            cur = {"key": key, "lo": int(r.Gen), "hi": int(r.Gen)}
            groups.append(cur)
    for g_ in groups:
        txt = str(g_["lo"]) if g_["lo"] == g_["hi"] else f"{g_['lo']}-{g_['hi']}"
        ax.annotate(txt, g_["key"], xytext=(4, 4), textcoords="offset points", fontsize=8, color=INK, zorder=6)
    ax.plot(path[:, 0], path[:, 1], color=MUTED, lw=1, zorder=2)
    ax.scatter([best.Sim_X], [best.Sim_Y], marker="*", s=300, color="#eb6834", edgecolor=INK, linewidth=0.8, zorder=5)
    ax.set_xlim(best.Sim_X - z, best.Sim_X + z)
    ax.set_ylim(best.Sim_Y + z, best.Sim_Y - z)
    ax.set_aspect("equal")
    ax.set_title(f"Zoom ±{int(z)} m around best ({best.PDR:.1f}%)", fontsize=11, color=INK, loc="left")
    ax.set_xlabel("Sim X (m)   [labels = generation(s) whose best was at that point]")
    # ---- (3) 수렴
    ax = axes[2]
    ax.plot(gs.Gen, gs.PDR_max, color="#2a78d6", lw=2, marker="o", ms=5, label="Best of generation")
    ax.plot(gs.Gen, gs.PDR_mean, color=MUTED, lw=1.5, ls="--", marker="o", ms=4, label="Mean of generation")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Single-RSU PDR (%)")
    ax.set_title("Convergence", fontsize=11, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=9)
    for x in axes:
        x.grid(color=GRID, lw=0.8)
        x.set_axisbelow(True)
        for s_ in ("top", "right"):
            x.spines[s_].set_visible(False)
    fig.tight_layout()
    png = os.path.join(a.out, "step3a_ga_generations_map.png")
    fig.savefig(png, dpi=170)
    print("저장:", png)

    try:
        import folium
    except ImportError:
        print("(folium 이 없어 HTML 지도는 건너뜀)")
        return
    from matplotlib.colors import to_hex

    lat0, lon0 = sim_eval.sim_to_latlon(best.Sim_X, best.Sim_Y)
    m = folium.Map(location=[lat0, lon0], zoom_start=14, tiles="CartoDB Positron")
    for _, r in d.iterrows():
        lat, lon = sim_eval.sim_to_latlon(r.Sim_X, r.Sim_Y)
        folium.CircleMarker([lat, lon], radius=4, color=to_hex(col[r.Gen]), fill=True, fill_opacity=0.8,
                            popup=f"Gen {int(r.Gen)} / ind {int(r.Ind_ID)} / PDR {r.PDR:.2f}%").add_to(m)
    folium.Marker([lat0, lon0], popup=f"GA best {best.PDR:.2f}%", icon=folium.Icon(color="orange", icon="star")).add_to(m)
    html = os.path.join(a.out, "step3a_ga_generations_map.html")
    m.save(html)
    print("저장:", html)


if __name__ == "__main__":
    main()
