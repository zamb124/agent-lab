"""Hang-guard xdist: один зависший gw не держит всю сессию до wall-clock pytest.

pytest-timeout ``thread`` убивает процесс на фазе call. Setup/teardown при
``func_only=true`` этим не покрыты. Master читает heartbeat воркеров и SIGKILL
процесс, который застрял в setup/call/teardown дольше timeout+slack.
Воркер в ``idle`` (ждёт следующую пачку тестов, пока сосед гоняет 180с) не трогаем.
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import TypedDict

import pytest

from core.types import JsonObject, require_json_object

_HEARTBEAT_DIR = Path("/tmp")
_HUNG_WORKER_DUMP = Path("/tmp/pytest-hung-worker.txt")
_SETUP_TEARDOWN_FLOOR_SECONDS = 60.0
_SLACK_SECONDS = 15.0
_MONITOR_PERIOD_SECONDS = 2.0

_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None
_killed_pids: set[int] = set()


class WorkerHeartbeat(TypedDict):
    worker: str
    pid: int
    nodeid: str
    phase: str
    timeout_sec: float
    monotonic: float
    time: float


def hung_worker_deadline_seconds(*, phase: str, timeout_sec: float) -> float:
    """Секунды с последнего heartbeat, после которых воркер считается зависшим."""
    if phase == "idle" or phase.startswith("session"):
        return float("inf")
    if timeout_sec <= 0:
        return float("inf")
    if phase in {"setup", "teardown"}:
        return max(timeout_sec, _SETUP_TEARDOWN_FLOOR_SECONDS) + _SLACK_SECONDS
    return timeout_sec + _SLACK_SECONDS


def heartbeat_is_hung(heartbeat: WorkerHeartbeat, *, now_monotonic: float) -> bool:
    age = now_monotonic - heartbeat["monotonic"]
    deadline = hung_worker_deadline_seconds(
        phase=heartbeat["phase"],
        timeout_sec=heartbeat["timeout_sec"],
    )
    return age > deadline


def _worker_label() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None or not worker.strip():
        return "master"
    if worker.startswith("gw"):
        return worker
    return f"gw{worker}"


def _heartbeat_path(worker: str | None = None) -> Path:
    label = worker if worker is not None else _worker_label()
    return _HEARTBEAT_DIR / f"platform_test_hang_guard_{label}.json"


def _timeout_seconds_for_item(item: pytest.Item) -> float:
    marker = item.get_closest_marker("timeout")
    if marker is not None and marker.args:
        return float(marker.args[0])
    raw: object = item.config.getini("timeout")
    if isinstance(raw, bool) or raw is None:
        raise ValueError("pytest timeout ini is required")
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError("pytest timeout ini is empty")
        return float(raw)
    if isinstance(raw, int | float):
        return float(raw)
    raise ValueError(f"pytest timeout ini has unexpected type: {type(raw)}")


def write_worker_heartbeat(
    nodeid: str,
    phase: str,
    *,
    timeout_sec: float,
) -> None:
    payload: WorkerHeartbeat = {
        "worker": _worker_label(),
        "pid": os.getpid(),
        "nodeid": nodeid,
        "phase": phase,
        "timeout_sec": timeout_sec,
        "monotonic": time.monotonic(),
        "time": time.time(),
    }
    path = _heartbeat_path()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _parse_heartbeat(raw: JsonObject) -> WorkerHeartbeat | None:
    worker = raw.get("worker")
    pid = raw.get("pid")
    nodeid = raw.get("nodeid")
    phase = raw.get("phase")
    timeout_sec = raw.get("timeout_sec")
    monotonic = raw.get("monotonic")
    stamp = raw.get("time")
    if not isinstance(worker, str) or not worker.strip():
        return None
    if not isinstance(pid, int) or pid <= 0:
        return None
    if not isinstance(nodeid, str) or not nodeid.strip():
        return None
    if not isinstance(phase, str) or not phase.strip():
        return None
    if not isinstance(timeout_sec, int | float):
        return None
    if not isinstance(monotonic, int | float):
        return None
    if not isinstance(stamp, int | float):
        return None
    return {
        "worker": worker,
        "pid": pid,
        "nodeid": nodeid,
        "phase": phase,
        "timeout_sec": float(timeout_sec),
        "monotonic": float(monotonic),
        "time": float(stamp),
    }


def _read_heartbeat(path: Path) -> WorkerHeartbeat | None:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        return _parse_heartbeat(require_json_object(loaded, path.name))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_hung_worker(heartbeat: WorkerHeartbeat, *, age: float) -> None:
    pid = heartbeat["pid"]
    if pid in _killed_pids:
        return
    if pid == os.getpid():
        return
    if heartbeat["worker"] == "master":
        return
    if not _pid_alive(pid):
        return
    line = (
        f"hang_guard SIGKILL worker={heartbeat['worker']} pid={pid} "
        f"phase={heartbeat['phase']} age={age:.1f}s timeout={heartbeat['timeout_sec']}s "
        f"test={heartbeat['nodeid']}\n"
    )
    print(f"\n=== {line.strip()} ===\n", flush=True)
    _HUNG_WORKER_DUMP.write_text(line, encoding="utf-8")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    _killed_pids.add(pid)


def _monitor_loop() -> None:
    while not _stop_event.wait(timeout=_MONITOR_PERIOD_SECONDS):
        now = time.monotonic()
        for path in sorted(_HEARTBEAT_DIR.glob("platform_test_hang_guard_*.json")):
            heartbeat = _read_heartbeat(path)
            if heartbeat is None:
                continue
            if not heartbeat_is_hung(heartbeat, now_monotonic=now):
                continue
            age = now - heartbeat["monotonic"]
            _kill_hung_worker(heartbeat, age=age)


def pytest_sessionstart(session: pytest.Session) -> None:
    write_worker_heartbeat("session", "session_start", timeout_sec=0)
    if hasattr(session.config, "workerinput"):
        return
    global _monitor_thread
    _stop_event.clear()
    _killed_pids.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="platform-test-hang-guard",
        daemon=True,
    )
    _monitor_thread.start()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _ = exitstatus
    write_worker_heartbeat("session", "session_finish", timeout_sec=0)
    if hasattr(session.config, "workerinput"):
        return
    _stop_event.set()
    if _monitor_thread is not None:
        _monitor_thread.join(timeout=1.0)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    write_worker_heartbeat(item.nodeid, "setup", timeout_sec=_timeout_seconds_for_item(item))
    yield
    write_worker_heartbeat(item.nodeid, "idle", timeout_sec=_timeout_seconds_for_item(item))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    write_worker_heartbeat(item.nodeid, "call", timeout_sec=_timeout_seconds_for_item(item))
    yield
    write_worker_heartbeat(item.nodeid, "idle", timeout_sec=_timeout_seconds_for_item(item))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, object, object]:
    write_worker_heartbeat(item.nodeid, "teardown", timeout_sec=_timeout_seconds_for_item(item))
    yield
    write_worker_heartbeat(item.nodeid, "idle", timeout_sec=_timeout_seconds_for_item(item))
