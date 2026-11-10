# -*- coding: utf-8 -*-
"""
rsu_lib/surrogate.py
================================================================
OMNeT++ 시뮬레이션 없이 RSU 배치를 빠르게 평가하는 "근사 평가 모델(surrogate)".
Veins 설정(config.xml / omnetpp_template.ini)의 전파 모델을 파이썬으로 그대로 재현한다.

  수신 세기(dBm) = 송신출력(50mW=17dBm) + 안테나이득(송·수신 monopole 평균)
                  + 자유공간 손실 20·log10(λ / 4πd)        (SimplePathlossModel, α=2)
                  − 건물 감쇠 (벽 1번 통과당 9dB + 건물 내부 1m당 0.4dB)  (SimpleObstacleShadowing)
  수신 성공 ⇔ 수신 세기 ≥ 임계값 (minPowerLevel = −89 dBm, 필요하면 보정)

차량 스냅샷(2초 간격 차량 위치) 각 점을 "그 시각 그 차량"으로 보고,
  커버 비율 = 1개 이상의 RSU 신호를 받을 수 있는 스냅샷 점의 비율
을 서비스 비율(Service_Ratio)의 근사치로 쓴다. (간섭은 무시: step2에서 η≈0 확인됨)

외부 의존성 없음(numpy, pandas만). 좌표는 전부 시뮬레이션 좌표(Sim_X, Sim_Y).
================================================================
"""
import math
import os
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

# 좌표 변환 (rsu_lib/coord_transform.py 와 동일)
OFFSET_X, OFFSET_Y = 644465.09, 5491786.25
HEIGHT, MARGIN = 3009.73, 25.0

# 전파 파라미터 (omnetpp_template.ini / config.xml / antenna.xml)
FREQ = 5.89e9
WAVELEN = 299792458.0 / FREQ
TX_DBM = 10 * math.log10(50.0)          # RSU 50 mW
ANT_GAIN_DB = 2 * -1.75                 # monopole 샘플 평균(약 −1.75dB) × 송·수신
DB_PER_CUT, DB_PER_M = 9.0, 0.4
THRESH_DBM = -89.0
MAX_RANGE = 700.0                       # 자유공간에서도 이 밖은 −89dBm 미만 (≈540m) → 계산 생략


def utm_to_sim(x, y):
    return x - OFFSET_X + MARGIN, HEIGHT - (y - OFFSET_Y) + MARGIN


def set_map(net_xml):
    """다른 지도: net.xml 의 convBoundary(xmin, ymin, xmax, ymax)로 좌표 변환 상수 교체 (Erlangen이면 값 그대로)"""
    global OFFSET_X, OFFSET_Y, HEIGHT
    from rsu_lib.scenario import boundary
    x0, y0, x1, y1 = boundary(net_xml)
    OFFSET_X, OFFSET_Y, HEIGHT = x0, y0, y1 - y0


def load_buildings(poly_xml):
    """건물 폴리곤 목록 → [np.array (n,2) 시뮬 좌표, 닫힌 다각형]"""
    polys = []
    for p in ET.parse(poly_xml).getroot().iter("poly"):
        if p.get("type") != "building":
            continue
        pts = [tuple(map(float, s.split(","))) for s in p.get("shape").split()]
        arr = np.array([utm_to_sim(x, y) for x, y in pts])
        if len(arr) >= 3:
            if not np.allclose(arr[0], arr[-1]):
                arr = np.vstack([arr, arr[:1]])
            polys.append(arr)
    return polys


def load_points(snap_csv):
    d = pd.read_csv(snap_csv, encoding="utf-8-sig")
    sx, sy = utm_to_sim(d.x.to_numpy(), d.y.to_numpy())
    return np.c_[sx, sy], d


class Surrogate:
    def __init__(self, poly_xml, snap_csv, thresh_dbm=THRESH_DBM, gain_db=ANT_GAIN_DB):
        self.polys = load_buildings(poly_xml)
        self.pts, self.snap = load_points(snap_csv)
        self.thresh = thresh_dbm
        self.gain = gain_db
        # 모든 건물 변(edge)을 한 배열로: (E,4) x1,y1,x2,y2 + 건물 번호
        segs, owner = [], []
        for b, P in enumerate(self.polys):
            segs.append(np.c_[P[:-1], P[1:]])
            owner.append(np.full(len(P) - 1, b))
        self.edges = np.vstack(segs)
        self.edge_owner = np.concatenate(owner)
        self.bbox = np.array([[P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()] for P in self.polys])
        self._cache = {}

    # ---------- 전파 ----------
    def _obstacle_loss(self, s, pts):
        """송신점 s(2,) → 수신점들 pts(n,2) 직선이 건물을 지나며 생기는 감쇠(dB) (Veins Obstacle 방식)"""
        n = len(pts)
        loss = np.zeros(n)
        if n == 0:
            return loss
        # 후보 건물: 선분 묶음의 bbox와 겹치는 것만
        lo = np.minimum(pts.min(0), s) - 1
        hi = np.maximum(pts.max(0), s) + 1
        bsel = np.where((self.bbox[:, 2] >= lo[0]) & (self.bbox[:, 0] <= hi[0]) &
                        (self.bbox[:, 3] >= lo[1]) & (self.bbox[:, 1] <= hi[1]))[0]
        if len(bsel) == 0:
            return loss
        emask = np.isin(self.edge_owner, bsel)
        E = self.edges[emask]
        own = self.edge_owner[emask]
        # 선분 교차: p = s + t (q - s), e = a + u (b - a), t,u ∈ [0,1]
        d = pts - s                       # (n,2)
        a, b = E[:, :2], E[:, 2:]
        e = b - a                         # (m,2)
        denom = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]   # (n,m)
        as_ = a[None, :, :] - s[None, None, :]                                    # (1,m,2)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (as_[..., 0] * e[None, :, 1] - as_[..., 1] * e[None, :, 0]) / denom
            u = (as_[..., 0] * d[:, None, 1] - as_[..., 1] * d[:, None, 0]) / denom
        hit = (np.abs(denom) > 1e-12) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
        rows = np.where(hit.any(1))[0]
        if len(rows) == 0:
            return loss
        dist = np.hypot(d[:, 0], d[:, 1])
        for i in rows:
            cols = np.where(hit[i])[0]
            tb = t[i, cols]
            ob = own[cols]
            cuts = len(cols)
            frac = 0.0
            for bid in np.unique(ob):
                ts = np.sort(tb[ob == bid])
                if len(ts) % 2 == 1:      # 끝점이 건물 안 → 끝(1)까지 내부로 처리
                    ts = np.append(ts, 1.0)
                frac += float(np.sum(ts[1::2] - ts[0::2]))
            loss[i] = DB_PER_CUT * cuts + DB_PER_M * frac * dist[i]
        return loss

    def rx_dbm(self, rsu):
        """RSU 한 개(Sim 좌표) → 모든 스냅샷 점의 수신 세기(dBm). 범위 밖은 −inf"""
        key = (round(float(rsu[0]), 1), round(float(rsu[1]), 1))
        if key in self._cache:
            return self._cache[key]
        s = np.array(key)
        dd = np.hypot(self.pts[:, 0] - s[0], self.pts[:, 1] - s[1])
        out = np.full(len(self.pts), -np.inf)
        idx = np.where(dd <= MAX_RANGE)[0]
        if len(idx):
            dist = np.maximum(dd[idx], 1.0)
            pr = TX_DBM + self.gain + 20 * np.log10(WAVELEN / (4 * math.pi * dist))
            # 자유공간만으로도 임계값 미달이면 건물 계산 생략
            need = pr >= self.thresh - 0.0
            sub = idx[need]
            pr2 = pr.copy()
            pr2[need] -= self._obstacle_loss(s, self.pts[sub])
            out[idx] = pr2
        self._cache[key] = out
        return out

    def covered(self, rsu):
        return self.rx_dbm(rsu) >= self.thresh

    # ---------- 배치 평가 ----------
    def evaluate(self, coords):
        """coords: [(x,y),...] → dict(커버비율%, RSU별 단독 커버, 새로 덮은 수 등)"""
        if len(coords) == 0:
            return {"Cover_pct": 0.0}
        cov = np.vstack([self.covered(c) for c in coords])
        anyc = cov.any(0)
        per = cov.sum(1)
        # 각 점을 가장 센 RSU에 배정했을 때 RSU별 담당량 (중복 없는 기여)
        rx = np.vstack([self.rx_dbm(c) for c in coords])
        best = np.where(anyc, rx.argmax(0), -1)
        own = np.array([(best == i).sum() for i in range(len(coords))])
        jain = (own.sum() ** 2) / (len(own) * (own ** 2).sum()) if (own ** 2).sum() > 0 else float("nan")
        mean_rx = float(np.mean(rx.max(0)[anyc])) if anyc.any() else float("nan")
        return {"Cover_pct": 100 * anyc.mean(), "Cover_pts": int(anyc.sum()),
                "PerRSU_cover": per.tolist(), "PerRSU_own": own.tolist(),
                "Jain_own": jain, "Overlap_pct": 100 * float((cov.sum(0) >= 2).mean()),
                "RSSI_mean_pred": mean_rx}

    def cover_pct(self, coords):
        if len(coords) == 0:
            return 0.0
        anyc = np.zeros(len(self.pts), bool)
        for c in coords:
            anyc |= self.covered(c)
        return 100 * anyc.mean()
