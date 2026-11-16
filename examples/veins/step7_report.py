#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step7_report.py   (시뮬레이션 0회, 몇 초) — 노션에 바로 붙일 수 있는 결과 정리(md) 자동 생성
================================================================
11/16 피드백 반영
  - 지표: 서비스 비율(중복 제외 "몇 대가 받았나") / 유효 수신량(같은 정보, 개수) / 총 수신량(중복 포함 "몇 번 받았나") / 중복도
  - 순위 3가지: 서비스만 / 모든 지표(시간 제외) / 모든 지표 + 시간
  - 시간: 근사 모델 기반(이번 방법들)과 시뮬레이션 기반(예전 algo2·3·4)을 나눠서 비교
  - GA 버전 비교: ① algo4(시뮬레이션 기반) ② v1 ③ v2 ④ v3(제안)
  - 최적해 검증: 전수조사(K≤6) = ILP
출력: experiment_results/step5/analysis/report.md  (+ report_*.csv)
실행: python3 step7_report.py            (집합 GA 등 제외 목록은 step5_analyze.EXCLUDE)
================================================================
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import step5_analyze as SA  # noqa: E402

OUT, AN = SA.OUT, SA.AN
LBL = {"Greedy-교차로": "교차로 정보 기반 (algo1 수정)", "Greedy-전체교차로": "밀도 스냅샷 기반 (algo7 수정)",
       "GA-연속그룹 v3": "**연속 GA v3 (제안)**", "GA-그룹 (교차점)": "GA (제안, 교차점 후보 = 최적해와 같은 조건)", "GA-연속그룹": "연속 GA v2", "GA-연속그룹 (기존 연산)": "연속 GA v1 (기존 연산)",
       "PPO": "PPO", "DQN": "DQN", "최적해(ILP)": "최적해 (전수조사 = ILP)", "Grid top-K": "격자 top-K",
       "GA-집합 (도로점)": "집합 GA"}
ORDER = list(LBL)
MAPS = {"": "에를랑겐", "DA": "담슈타트", "GN": "강남"}
PATN = {"P1": "트래픽1 (P1 랜덤)", "P2": "트래픽2 (P2 도심 집중)", "P3": "트래픽3 (P3 간선 통과)"}


def mapof(p):
    return MAPS.get(p.split("_")[0] if "_" in p else "", "에를랑겐")


def mdtab(df):
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |")
    return "\n".join(lines)


def ranks(S):
    """(패턴, K)마다 3가지 순위"""
    out = []
    for (p, K), b in S.groupby(["Pattern", "K"]):
        b = b.reset_index(drop=True)
        r_s = b.Service_Ratio_mean.rank(ascending=False, method="min")
        r_m = pd.Series(SA.norm_score(b, SA.MET)).rank(ascending=False, method="min")
        r_t = pd.Series(SA.norm_score(b, SA.MET + [SA.TIME])).rank(ascending=False, method="min")
        for i, r in b.iterrows():
            out.append(dict(Pattern=p, K=K, Method=r.Method, R_service=r_s[i], R_metrics=r_m[i], R_all=r_t[i]))
    return pd.DataFrame(out)


def fmt(v, dec):
    return f"{v:,.{dec}f}"


def main():
    S, raw, T = SA.load()
    S = S[~S.Method.isin(SA.EXCLUDE)].copy()
    T = T[~T.Method.isin(SA.EXCLUDE)].copy()
    R = ranks(S)
    S = S.merge(R, on=["Pattern", "K", "Method"])
    R.to_csv(os.path.join(AN, "report_ranks.csv"), index=False, encoding="utf-8-sig")
    doc = ["# 실험 결과 정리 (자동 생성: step7_report.py)", "",
           "- 값: 5회 반복 평균 ± 표준편차. 순위는 K마다 매긴 순위를 K=1~10 평균 (낮을수록 좋음)",
           "- 서비스만 = 서비스 비율 순위 / 모든 지표 = 서비스·총수신·Jain RSU·Jain 차량 / +시간 = 여기에 계산 시간 추가",
           "- RSSI·PER·충돌·채널 점유율은 표에만 표시하고 순위에서 제외: PER·충돌·점유율은 모든 방법이 거의 0이라 차이가 무의미하고, RSSI는 성공 수신만 평균이라 넓게 덮을수록 낮아지는 편향이 있음 (아래 '지표별 방법 간 차이 크기' 참고)",
           "- 유효 수신량 = BSM을 1개 이상 받은 차량-0.1초 칸 수(중복 제외), 총 수신량 = 받은 BSM 전부(중복 포함), 중복도 = 총 ÷ 유효", ""]
    pats = sorted(S.Pattern.unique(), key=lambda p: (list(MAPS.values()).index(mapof(p)), p))
    for mp in [m for m in MAPS.values() if any(mapof(p) == m for p in pats)]:
        doc += [f"## {mp}", ""]
        mps = [p for p in pats if mapof(p) == mp]
        for p in mps:
            d = S[S.Pattern == p]
            meths = [m for m in ORDER if m in set(d.Method)]
            doc += [f"### {PATN.get(p.split('_')[-1], p)}", "", "**표 A. 서비스 비율(%)와 순위**", ""]
            rows = []
            for m in meths:
                q = d[d.Method == m].set_index("K")
                cells = {f"K={k}": (f"{q.loc[k, 'Service_Ratio_mean']:.1f} ± {q.loc[k, 'Service_Ratio_std']:.2f}" if k in q.index else "–") for k in range(1, 11)}
                rows.append(dict(방법=LBL[m], **cells, 평균=round(q.Service_Ratio_mean.mean(), 1),
                                 서비스만=round(q.R_service.mean(), 1), 모든지표=round(q.R_metrics.mean(), 1), 모든지표_시간=round(q.R_all.mean(), 1)))
            doc += [mdtab(pd.DataFrame(rows)), "", "**표 B. 나머지 지표 (K=1~10 평균 ± 반복 표준편차 평균)**", ""]
            cols = [("Effective_Received", "유효 수신량", 0), ("Total_Received", "총 수신량", 0), ("Duplication", "중복도", 2),
                    ("PDR", "PDR(%)", 1), ("Jain_RSU", "Jain RSU", 3), ("Jain_Vehicle", "Jain 차량", 3), ("RSSI_Mean_dBm", "RSSI(dBm)", 1),
                    ("PER", "PER(%)", 3), ("Collisions", "충돌 수", 2), ("Channel_Busy", "채널 점유율(%)", 3)]
            rows = []
            for m in meths:
                q = d[d.Method == m]
                rows.append({"방법": LBL[m], **{lab: f"{fmt(q[k + '_mean'].mean(), dec)} ± {fmt(q[k + '_std'].mean(), dec)}"
                                               for k, lab, dec in cols if k + "_mean" in q}})
            doc += [mdtab(pd.DataFrame(rows)), ""]
            good = d[~d.Method.isin(["Grid top-K", "GA-연속그룹 (기존 연산)"])]
            w = good.loc[good.groupby("K").Service_Ratio_mean.idxmax()]
            r1 = d[d.R_all == 1].groupby("Method").size().sort_values(ascending=False)
            k80 = {LBL[m]: good[(good.Method == m) & (good.Service_Ratio_mean >= 80)].K.min() for m in good.Method.unique()}
            doc += ["- 자동 요약",
                    "  - K별 서비스 1위: " + ", ".join(f"K={k} {LBL[m]}" for k, m in zip(w.K, w.Method)),
                    "  - 모든 지표+시간 1위 횟수: " + ", ".join(f"{LBL[m]} {n}번" for m, n in r1.items()),
                    "  - 서비스 80% 달성 K: " + ", ".join(f"{m} {('–' if pd.isna(k) else int(k))}개" for m, k in k80.items()), ""]
        # 지도 전체 순위
        d = S[S.Pattern.isin(mps)]
        g = d.groupby("Method").agg(svc=("Service_Ratio_mean", "mean"), rs=("R_service", "mean"), rm=("R_metrics", "mean"), ra=("R_all", "mean"))
        g = g.reindex([m for m in ORDER if m in g.index])
        tab = pd.DataFrame({"방법": [LBL[m] for m in g.index], "평균 서비스(%)": g.svc.round(1),
                            "서비스만 순위": g.rs.round(2), "모든 지표 순위": g.rm.round(2), "모든 지표+시간 순위": g.ra.round(2)})
        doc += [f"### {mp} 전체 (트래픽 {len(mps)}개 × K=1~10)", "", mdtab(tab.sort_values("서비스만 순위")), ""]
        # 시간
        t = T[T.Pattern.isin(mps)]
        rows = []
        for m in [m for m in ORDER if m in set(t.Method)]:
            q = t[t.Method == m]
            per = q.groupby("Pattern").agg(prep=("Prep_s", "first"), train=("Train_s", "first"), sk=("Time_K_s", "sum"))
            kt = q.groupby("K").Time_K_s.mean()
            rows.append({"방법": LBL[m], **{f"K={k}": f"{kt.get(k, np.nan):.3g}" if k in kt else "–" for k in range(1, 11)},
                         "준비": round(per.prep.mean(), 1), "학습": round(per.train.mean(), 1),
                         "전체(트래픽당)": round((per.prep + per.train + per.sk).mean(), 1)})
        doc += [f"### {mp} 계산 시간 (초, 트래픽 평균; 모두 근사 모델 기반)", "", mdtab(pd.DataFrame(rows)), ""]
        # 최적해 검증
        oc = [pd.read_csv(f) for p in mps for f in glob.glob(os.path.join(OUT, p, "optimal_check.csv"))]
        if oc:
            oc = pd.concat(oc)
            doc += [f"### {mp} 최적해 검증 (교차점 후보, 근사 모델 커버 %)", "",
                    mdtab(oc.assign(일치=oc.Same.map({True: "같음", False: "–"}))[["Pattern", "K", "ILP_cover", "BF_cover", "BF_finished", "BF_s", "일치"]]), ""]
    # 지표별 방법 간 차이 크기 (순위에서 뺀 이유의 근거)
    rows = []
    for k, lab, unit in (("Service_Ratio", "서비스 비율", "%p"), ("Total_Received", "총 수신량", "개"), ("Jain_Vehicle", "Jain 차량", ""),
                         ("RSSI_Mean_dBm", "RSSI", "dB"), ("PER", "PER", "%p"), ("Collisions", "충돌 수", "회/200초"),
                         ("Channel_Busy", "채널 점유율", "%p")):
        g = S.groupby(["Pattern", "K"])[k + "_mean"]
        sp = (g.max() - g.min()).mean()
        rows.append(dict(지표=lab, 방법간_최대최소차이_평균=f"{sp:,.4g} {unit}", 값의_범위=f"{S[k + '_mean'].min():,.4g} ~ {S[k + '_mean'].max():,.4g}",
                         순위반영="O" if k in [m for m, _, _ in SA.MET] else "X (표에만)"))
    doc += ["## 지표별 방법 간 차이 크기 (같은 K 안에서)", "", mdtab(pd.DataFrame(rows)), ""]
    # GA 버전 비교
    doc += ["## GA 버전 비교", ""]
    rows = []
    sim_k1 = raw[(raw.K == 1) & (raw.Pattern == "P1")].Elapsed_Sec.mean() if len(raw) else np.nan
    a4 = os.path.join("experiment_results", "single", "algo4", "algo4_GA_hybrid_corrected", "ga_hybrid_final_results_corrected.csv")
    if os.path.exists(a4):
        g4 = pd.read_csv(a4)
        rows.append(dict(버전="① algo4 (시뮬레이션 기반, K=1만)", 평가="시뮬레이터", 평가횟수=len(g4),
                         K1_PDR=round(g4.PDR.max(), 2), 평균서비스="–", 서비스만순위="–",
                         K당시간=f"약 {len(g4) * sim_k1:.0f}s (시뮬 {len(g4)}회 × {sim_k1:.0f}s)"))
    for m, lab in (("GA-연속그룹 (기존 연산)", "② v1 (좌표 평균 교차)"), ("GA-연속그룹", "③ v2 (RSU 단위 교차, 매번 계산)"),
                   ("GA-연속그룹 v3", "④ v3 (제안, 커버 지도 미리 계산)"), ("GA-그룹 (교차점)", "④' v3 같은 GA, 교차점 후보")):
        d = S[S.Method == m]
        if d.empty:
            continue
        t = T[T.Method == m]
        k1 = d[(d.K == 1) & (d.Pattern == "P1")]
        rows.append(dict(버전=lab, 평가="근사 모델", 평가횟수="–",
                         K1_PDR=round(k1.PDR_mean.iloc[0], 2) if len(k1) else "–",
                         평균서비스=round(d.Service_Ratio_mean.mean(), 1), 서비스만순위=round(d.R_service.mean(), 2),
                         K당시간=f"{t.Time_K_s.mean():.1f}s (+준비 {t.Prep_s.fillna(0).groupby(t.Pattern).first().mean():.0f}s)"))
    doc += [mdtab(pd.DataFrame(rows)), "", "- K1_PDR = 에를랑겐 P1, RSU 1개일 때 실측 PDR (algo4와 같은 조건 비교용)", ""]
    # 시뮬레이션 기반 vs 근사 모델 기반 (P1, K=1)
    old = [("algo2 격자 전수조사", "algo2/algo2_grid_shifted_corrected/bruteforce_grid_shifted_corrected.csv"),
           ("algo3 SA", "algo3/algo3_SA_standard_corrected/algo3_sa_results_corrected.csv"),
           ("algo4 GA", "algo4/algo4_GA_hybrid_corrected/ga_hybrid_final_results_corrected.csv")]
    rows = []
    for lab, f in old:
        f = os.path.join("experiment_results", "single", f)
        if os.path.exists(f):
            o = pd.read_csv(f)
            c = [x for x in o.columns if "PDR" in x.upper()][0]
            rows.append(dict(그룹="시뮬레이션 기반", 방법=lab, 시뮬레이션횟수=len(o), K1_PDR=round(o[c].max(), 2), 시간=f"약 {len(o) * sim_k1 / 60:.0f}분"))
    for m in [m for m in ORDER if m in set(S.Method)]:
        k1 = S[(S.Method == m) & (S.K == 1) & (S.Pattern == "P1")]
        t = T[(T.Method == m) & (T.K == 1) & (T.Pattern == "P1")]
        if len(k1) and len(t):
            rows.append(dict(그룹="근사 모델 기반", 방법=LBL[m], 시뮬레이션횟수=0, K1_PDR=round(k1.PDR_mean.iloc[0], 2),
                             시간=f"{(t.Prep_s.fillna(0) + t.Train_s.fillna(0) + t.Time_K_s).iloc[0]:.1f}초"))
    doc += ["## 시뮬레이션 기반 vs 근사 모델 기반 (에를랑겐 P1, K=1)", "",
            "- 시뮬레이션 기반은 위치 후보마다 시뮬레이터를 돌려서 느릴 수밖에 없음 → 같은 시간 기준으로 순위를 매기지 않고 따로 표기",
            f"- 시간은 시뮬레이션 1회 평균 {sim_k1:.0f}초로 환산", "", mdtab(pd.DataFrame(rows)), ""]
    with open(os.path.join(AN, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(doc))
    print("\n".join(doc[:60]))
    print(f"\n완료 → {os.path.join(AN, 'report.md')}")


if __name__ == "__main__":
    main()
