from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_PROFILE_ENV = "PLATFORM_TEST_PROFILE_RUNTIME"
_LOCK_WARN_MS = float(os.environ.get("PLATFORM_TEST_PROFILE_LOCK_WARN_MS", "50"))
_LOOP_WARN_MS = float(os.environ.get("PLATFORM_TEST_PROFILE_LOOP_WARN_MS", "25"))


@dataclass(slots=True)
class LockWaitSample:
    lock_path: str
    wait_ms: float
    acquired: bool
    worker: str
    test_nodeid: str
    phase: str
    monotonic_at: float


@dataclass(slots=True)
class SlowLoopSample:
    message: str
    duration_ms: float | None
    worker: str
    test_nodeid: str
    monotonic_at: float


@dataclass
class RuntimeProfileCollector:
    lock_waits: list[LockWaitSample] = field(default_factory=list)
    slow_loop: list[SlowLoopSample] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _current_test_nodeid: str = field(default="session", repr=False)

    def set_current_test(self, nodeid: str) -> None:
        with self._lock:
            self._current_test_nodeid = nodeid

    def current_test(self) -> str:
        with self._lock:
            return self._current_test_nodeid

    def record_lock_wait(
        self,
        *,
        lock_path: str,
        wait_sec: float,
        acquired: bool,
        phase: str,
    ) -> None:
        wait_ms = wait_sec * 1000.0
        if wait_ms < _LOCK_WARN_MS:
            return
        sample = LockWaitSample(
            lock_path=lock_path,
            wait_ms=wait_ms,
            acquired=acquired,
            worker=_worker_label(),
            test_nodeid=self.current_test(),
            phase=phase,
            monotonic_at=time.monotonic(),
        )
        with self._lock:
            self.lock_waits.append(sample)

    def record_slow_loop(self, message: str, duration_ms: float | None) -> None:
        if duration_ms is not None and duration_ms < _LOOP_WARN_MS:
            return
        sample = SlowLoopSample(
            message=message,
            duration_ms=duration_ms,
            worker=_worker_label(),
            test_nodeid=self.current_test(),
            monotonic_at=time.monotonic(),
        )
        with self._lock:
            self.slow_loop.append(sample)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            lock_waits = [asdict(item) for item in self.lock_waits]
            slow_loop = [asdict(item) for item in self.slow_loop]
        lock_waits.sort(key=lambda row: float(row["wait_ms"]), reverse=True)
        slow_loop.sort(
            key=lambda row: float(row["duration_ms"] if row["duration_ms"] is not None else 0.0),
            reverse=True,
        )
        return {
            "worker": _worker_label(),
            "lock_warn_ms": _LOCK_WARN_MS,
            "loop_warn_ms": _LOOP_WARN_MS,
            "lock_waits": lock_waits,
            "slow_loop": slow_loop,
        }

    def write_report(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


_collector = RuntimeProfileCollector()


def profiling_enabled() -> bool:
    return os.environ.get(_PROFILE_ENV) == "1"


def get_collector() -> RuntimeProfileCollector:
    return _collector


def _worker_label() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return "master"
    if worker.startswith("gw"):
        return worker
    return f"gw{worker}"


def default_report_path() -> Path:
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    return Path(f"/tmp/platform_test_runtime_profile_{worker}.json")


def merge_worker_reports(report_paths: list[Path]) -> dict[str, object]:
    lock_waits: list[dict[str, object]] = []
    slow_loop: list[dict[str, object]] = []
    workers: list[str] = []
    for report_path in report_paths:
        if not report_path.is_file():
            continue
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        workers.append(str(payload.get("worker", report_path.stem)))
        lock_waits_payload = payload.get("lock_waits")
        slow_loop_payload = payload.get("slow_loop")
        if isinstance(lock_waits_payload, list):
            lock_waits.extend(row for row in lock_waits_payload if isinstance(row, dict))
        if isinstance(slow_loop_payload, list):
            slow_loop.extend(row for row in slow_loop_payload if isinstance(row, dict))
    lock_waits.sort(key=lambda row: float(row.get("wait_ms", 0.0)), reverse=True)
    slow_loop.sort(
        key=lambda row: float(row.get("duration_ms") or 0.0),
        reverse=True,
    )
    return {
        "workers": workers,
        "lock_waits": lock_waits,
        "slow_loop": slow_loop,
    }
