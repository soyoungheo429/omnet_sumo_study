# -*- coding: utf-8 -*-
"""
rsu_lib/naming.py
================================================================
파라미터 조합을 "이어붙이는 방식"으로 파일명/로그명을 일관되게 생성.
같은 규칙을 모든 알고리즘/모든 결과 파일이 공유해야 나중에 검색/비교가 쉬움.

이름 형식 (콜론(:) 없이 언더바로 key=value를 이어붙임):
    {algo}_{mode}_{param1}-{val1}_{param2}-{val2}_{date}_{run_id}

예:
    algo7_multi_K8_bitrate-6M_sync-True_20260928_run01
"""

import os
import datetime
import uuid


def build_name(
    algo: str, mode: str, params: dict, date: str = None, run_id: str = None
) -> str:
    """파라미터 딕셔너리를 알파벳 순으로 정렬해 이어붙여 이름을 만든다.
    순서를 알파벳순으로 고정하는 이유: 호출할 때마다 dict 순서가 달라져도
    항상 같은 이름이 나오게 하기 위함 (재현성)."""
    if date is None:
        date = datetime.date.today().strftime("%Y%m%d")
    if run_id is None:
        run_id = uuid.uuid4().hex[:6]

    param_str = "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
    parts = [algo, mode]
    if param_str:
        parts.append(param_str)
    parts.append(date)
    parts.append(run_id)
    return "_".join(str(p) for p in parts)


def result_paths(base_dir: str, name: str) -> dict:
    """이름 하나로부터 이 실행에서 쓸 모든 산출물 경로를 일관되게 생성.
    raw/trend/plot/log가 항상 같은 접두어(name)를 공유하므로, 파일 목록만
    봐도 어느 실행에서 나온 건지 바로 알 수 있다."""
    run_dir = os.path.join(base_dir, name)
    os.makedirs(run_dir, exist_ok=True)
    return {
        "dir": run_dir,
        "raw_csv": os.path.join(run_dir, f"{name}_raw.csv"),
        "trend_csv": os.path.join(run_dir, f"{name}_trend.csv"),
        "plot_png": os.path.join(run_dir, f"{name}_plot.png"),
        "log_txt": os.path.join(run_dir, f"{name}_log.txt"),
        "config_snapshot_ini": os.path.join(run_dir, f"{name}_config.ini"),
    }


if __name__ == "__main__":
    name = build_name(
        algo="algo7",
        mode="multi",
        params={"K": 8, "bitrate": "6M", "sync": True},
        run_id="run01",
    )
    print(name)
    print(result_paths("results", name))
