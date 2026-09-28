# -*- coding: utf-8 -*-
"""
rsu_lib/run_logger.py
================================================================
교수님 피드백: "1번 실행할 때 최대한 많은(다양한) 로그 dump가 쌓이게"
-> 매 실행마다 아래를 전부 한 곳(JSON)에 남긴다:
   - 언제 실행했는지, 어떤 git commit 상태였는지
   - 어떤 파라미터로 실행했는지 (naming.py의 params와 동일)
   - 반복(repeat)마다의 결과 이벤트
   - 실행 소요 시간, 성공/실패 여부
================================================================
"""

import sys
import json
import time
import subprocess
import datetime


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


class RunLogger:
    """with RunLogger(...) as log: ... 형태로 써서, 성공/실패와 무관하게
    항상 로그가 남도록 한다."""

    def __init__(self, log_path: str, algo: str, mode: str, params: dict):
        self.log_path = log_path
        self.record = {
            "algo": algo,
            "mode": mode,
            "params": params,
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "git_commit": get_git_commit(),
            "python": sys.version.split()[0],
            "events": [],
        }
        self._start_time = None

    def __enter__(self):
        self._start_time = time.time()
        self._flush()
        return self

    def log_event(self, **kwargs):
        """반복(repeat)마다 하나씩 호출 -> 로그가 "풍부하게" 쌓이는 지점."""
        kwargs["_t"] = round(time.time() - self._start_time, 2)
        self.record["events"].append(kwargs)
        self._flush()

    def log_stdout(self, text: str):
        self.record.setdefault("raw_stdout_chunks", []).append(text)
        self._flush()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.record["finished_at"] = datetime.datetime.now().isoformat(
            timespec="seconds"
        )
        self.record["elapsed_sec"] = round(time.time() - self._start_time, 2)
        self.record["status"] = "error" if exc_type else "success"
        if exc_type:
            self.record["error"] = f"{exc_type.__name__}: {exc_val}"
        self._flush()
        return False

    def _flush(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.record, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    with RunLogger(
        "example_log.json", algo="algo7", mode="multi", params={"K": 8, "bitrate": "6M"}
    ) as log:
        for r in range(1, 4):
            log.log_event(repeat=r, pdr=10.0 + r, total_generated=2000)
    print("example_log.json 생성됨")
