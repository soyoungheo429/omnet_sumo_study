# -*- coding: utf-8 -*-
"""
rsu_lib/sim_eval.py
================================================================
"좌표 리스트 → ini 생성 → 시뮬레이션 실행 → 전체 지표 파싱"을 한 번에 하는 공용 모듈
(3단계 GA / 조합 실험용). step2 의 run 로직과 같은 방식이다.

- omnetpp_template.ini 는 건드리지 않고, bitrate/sync 만 바꾼 복사본을 out_dir 에 만들어 쓴다.
- run 1개에 제한시간(timeout)을 두고, 걸리면 프로세스 그룹째 kill 한다.
- MockEvaluator: 시뮬레이션 없이 스크립트 로직만 점검할 때 쓰는 가짜 평가기 (--mock).
================================================================
"""
import csv
import math
import os
import re
import signal
import subprocess
import time

from rsu_lib import sim_runner

# 탐색 공간 (시뮬레이션 좌표계: 원본 x+25, y는 뒤집고 +25 — rsu_lib/coord_transform.py 와 동일)
WIDTH, HEIGHT, MARGIN = 2606.46, 3009.73, 25.0
OFFSET_X, OFFSET_Y = 644465.09, 5491786.25
X_MIN, X_MAX = MARGIN, WIDTH + MARGIN
Y_MIN, Y_MAX = MARGIN, HEIGHT + MARGIN


def sim_to_latlon(sx, sy):
    """시뮬레이션 좌표 → (lat, lon). folium 지도용."""
    from pyproj import Proj

    raw_x, raw_y = sx - MARGIN, HEIGHT - (sy - MARGIN)
    utm = Proj("+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
    lon, lat = utm(raw_x + OFFSET_X, raw_y + OFFSET_Y, inverse=True)
    return lat, lon


def make_template(out_dir, bitrate="6Mbps", sync=True, template="omnetpp_template.ini"):
    with open(template, "r", encoding="utf-8") as f:
        txt = f.read()
    txt, n1 = re.subn(r"^\*\.\*\*\.nic\.mac1609_4\.bitrate\s*=.*$",
                      f"*.**.nic.mac1609_4.bitrate = {bitrate}  # [step3]", txt, flags=re.M)
    txt, n2 = re.subn(r"^\*\.rsu\[\*\]\.appl\.avoidBeaconSynchronization\s*=.*$",
                      f"*.rsu[*].appl.avoidBeaconSynchronization = {'true' if sync else 'false'}  # [step3]",
                      txt, flags=re.M)
    if n1 != 1 or n2 != 1:
        raise SystemExit(f"{template}에서 bitrate({n1}개)/avoidBeaconSynchronization({n2}개) 줄을 정확히 1개씩 찾지 못했어요.")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"_template_{bitrate}_sync{sync}.ini")
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def _run_sim(timeout):
    t0 = time.time()
    p = subprocess.Popen([sim_runner.RUN_SCRIPT, "-u", "Cmdenv", "-c", "General"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
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
    return (p.returncode == 0 and "<!> Error" not in out), time.time() - t0, out


class SimEvaluator:
    def __init__(self, out_dir, bitrate="6Mbps", sync=True, timeout=1800):
        self.template = make_template(out_dir, bitrate, sync)
        self.timeout = timeout

    def evaluate(self, coords, seed):
        """coords: [(sim_x, sim_y), ...]. 반환: parse_all 결과 + Success/Elapsed_Sec/Error."""
        err, sec, res, ok = "", 0.0, dict(sim_runner.empty_result()), False
        for _ in (1, 2):  # 실패하면 1회 재시도
            sim_runner.write_ini(self.template, "omnetpp.ini", coords, len(coords), seed=seed)
            sim_runner.reset_results_dir()
            ok, sec, out = _run_sim(self.timeout)
            res = sim_runner.parse_all(coords) if ok else dict(sim_runner.empty_result())
            if ok and res.get("Total_Generated", 0) == 0:
                ok, err = False, "BSM이 하나도 생성되지 않음"
            elif not ok:
                err = out[-300:].replace("\n", " | ")
            if ok:
                break
        res.update(Success=ok, Elapsed_Sec=round(sec, 2), Error="" if ok else err[:300])
        return res


class MockEvaluator:
    """시뮬레이션 없이 로직 점검용. (1300,1370) 근처를 좋은 지점으로 보는 가짜 지표."""

    def evaluate(self, coords, seed):
        s = sum(math.exp(-((x - 1300) ** 2 + (y - 1370) ** 2) / (2 * 350.0 ** 2)) for x, y in coords)
        k = len(coords)
        rx = 30000 * (1 - math.exp(-s))
        res = dict(sim_runner.empty_result())
        res.update(Total_Generated=2000 * k, Num_Vehicles=47, Num_RSUs=k, Total_Received=int(rx),
                   Actual_Received=int(rx), PDR=round(rx / (2000 * k * 47) * 100, 4),
                   Service_Ratio=round(100 * (1 - math.exp(-1.2 * s)), 4), Jain_RSU=0.9, Jain_Vehicle=0.7,
                   PER=0.0, Collisions=0, RSSI_Mean_dBm=-76.0, SNR_Mean_dB=21.0, Channel_Busy=0.05,
                   PerRSU_Rx="[]", PerRSU_Source="mock", Metrics_OK=True, Success=True,
                   Elapsed_Sec=0.01, Error="")
        return res


def append_csv_row(path, cols, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval="")
        if new:
            w.writeheader()
        w.writerow(row)
