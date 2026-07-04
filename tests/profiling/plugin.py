from __future__ import annotations

import glob
import json
import os
import subprocess
import threading
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio

from tests.profiling.collector import (
    default_report_path,
    get_collector,
    merge_worker_reports,
    profiling_enabled,
)
from tests.profiling.filelock_patch import install_filelock_patch
from tests.profiling.loop_patch import install_loop_watchdog, try_install_on_running_loop

_HEARTBEAT_GLOB = "/tmp/platform_test_runtime_heartbeat_*.json"
_PROGRESS_PATH = Path("/tmp/platform_test_runtime_progress.json")
_STALL_SECONDS = float(os.environ.get("PLATFORM_TEST_PROFILE_STALL_SECONDS", "8"))
_stall_stop_event = threading.Event()
_stall_thread: threading.Thread | None = None


def pytest_configure(config: pytest.Config) -> None:
    if not profiling_enabled():
        return
    for stale_report in glob.glob("/tmp/platform_test_runtime_profile_*.json"):
        Path(stale_report).unlink(missing_ok=True)
    for stale_heartbeat in glob.glob(_HEARTBEAT_GLOB):
        Path(stale_heartbeat).unlink(missing_ok=True)
    _PROGRESS_PATH.unlink(missing_ok=True)
    install_filelock_patch()


def pytest_sessionstart(session: pytest.Session) -> None:
    if not profiling_enabled():
        return
    _write_progress("session_start")
    _write_heartbeat("session", "session_start")
    if not hasattr(session.config, "workerinput"):
        _start_stall_monitor()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    if profiling_enabled():
        get_collector().set_current_test(item.nodeid)
        _write_heartbeat(item.nodeid, "setup")
    yield


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    if profiling_enabled():
        get_collector().set_current_test(item.nodeid)
        _write_heartbeat(item.nodeid, "call")
    yield


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, object, object]:
    if profiling_enabled():
        get_collector().set_current_test(item.nodeid)
        _write_heartbeat(item.nodeid, "teardown")
    yield


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not profiling_enabled():
        return
    if report.when == "call":
        _write_progress(f"{report.outcome} {report.nodeid}")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _platform_runtime_loop_profile() -> AsyncGenerator[None, None]:
    if not profiling_enabled():
        yield
        return
    import asyncio

    loop = asyncio.get_running_loop()
    install_loop_watchdog(loop)
    yield
    try_install_on_running_loop()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not profiling_enabled():
        return

    _write_heartbeat("session", f"session_finish:{exitstatus}")
    _write_progress(f"session_finish:{exitstatus}")
    if not hasattr(session.config, "workerinput"):
        _stall_stop_event.set()
        if _stall_thread is not None:
            _stall_thread.join(timeout=1.0)

    report_path = default_report_path()
    get_collector().write_report(report_path)

    if hasattr(session.config, "workerinput"):
        return

    worker_reports = [
        Path(path)
        for path in glob.glob("/tmp/platform_test_runtime_profile_*.json")
    ]
    merged = merge_worker_reports(worker_reports)
    merged_path = Path("/tmp/platform_test_runtime_profile_merged.json")
    merged_path.write_text(
        __import__("json").dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _print_summary(merged, merged_path)


def _worker_label() -> str:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return "master"
    if worker.startswith("gw"):
        return worker
    return f"gw{worker}"


def _heartbeat_path() -> Path:
    return Path(f"/tmp/platform_test_runtime_heartbeat_{_worker_label()}.json")


def _write_heartbeat(nodeid: str, phase: str) -> None:
    payload = {
        "worker": _worker_label(),
        "pid": os.getpid(),
        "nodeid": nodeid,
        "phase": phase,
        "monotonic": time.monotonic(),
        "time": time.time(),
    }
    _heartbeat_path().write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_progress(label: str) -> None:
    payload = {
        "pid": os.getpid(),
        "label": label,
        "monotonic": time.monotonic(),
        "time": time.time(),
    }
    _PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_progress_monotonic() -> float:
    try:
        payload = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return time.monotonic()
    monotonic = payload.get("monotonic")
    if isinstance(monotonic, int | float):
        return float(monotonic)
    return time.monotonic()


def _start_stall_monitor() -> None:
    global _stall_thread
    _stall_stop_event.clear()
    _stall_thread = threading.Thread(
        target=_stall_monitor_loop,
        name="platform-test-stall-monitor",
        daemon=True,
    )
    _stall_thread.start()


def _stall_monitor_loop() -> None:
    last_reported_progress = 0.0
    while not _stall_stop_event.wait(timeout=1.0):
        progress_at = _read_progress_monotonic()
        stalled_for = time.monotonic() - progress_at
        if stalled_for < _STALL_SECONDS:
            continue
        if progress_at == last_reported_progress:
            continue
        last_reported_progress = progress_at
        _print_stall_snapshot(stalled_for)


def _print_stall_snapshot(stalled_for: float) -> None:
    print(f"\n=== PLATFORM TEST STALL {stalled_for:.1f}s (no completed call reports) ===")
    for heartbeat in sorted(Path("/tmp").glob("platform_test_runtime_heartbeat_*.json")):
        try:
            payload = json.loads(heartbeat.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        age = time.monotonic() - float(payload.get("monotonic") or 0.0)
        print(
            f"  {payload.get('worker')} pid={payload.get('pid')} "
            f"phase={payload.get('phase')} age={age:.1f}s "
            f"test={payload.get('nodeid')}"
        )
    top = subprocess.run(
        [
            "ps",
            "-axo",
            "pid,ppid,stat,etime,pcpu,pmem,command",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    rows = []
    for line in top.stdout.splitlines()[1:]:
        if "pytest" not in line and "granian" not in line and "taskiq" not in line:
            continue
        rows.append(line)
    if rows:
        print("  active platform processes:")
        for row in rows[:20]:
            print(f"    {row[:220]}")
    print("=== END PLATFORM TEST STALL ===\n")


def _print_summary(payload: dict[str, object], merged_path: Path) -> None:
    lock_waits = payload.get("lock_waits")
    slow_loop = payload.get("slow_loop")
    lock_rows = lock_waits if isinstance(lock_waits, list) else []
    slow_rows = slow_loop if isinstance(slow_loop, list) else []

    print("\n=== PLATFORM TEST RUNTIME PROFILE ===")
    print(f"merged report: {merged_path}")

    if lock_rows:
        print("\nFileLock waits (top 20):")
        for row in lock_rows[:20]:
            if not isinstance(row, dict):
                continue
            print(
                f"  {row.get('wait_ms', 0.0):.0f}ms "
                f"acquired={row.get('acquired')} "
                f"lock={row.get('lock_path')} "
                f"worker={row.get('worker')} "
                f"test={row.get('test_nodeid')}"
            )
    else:
        print("\nFileLock waits: (none above threshold)")

    if slow_rows:
        print("\nSlow event loop callbacks (top 20):")
        for row in slow_rows[:20]:
            if not isinstance(row, dict):
                continue
            duration_ms = row.get("duration_ms")
            duration_label = f"{float(duration_ms):.0f}ms" if duration_ms is not None else "?"
            print(
                f"  {duration_label} "
                f"worker={row.get('worker')} "
                f"test={row.get('test_nodeid')} "
                f"{row.get('message')}"
            )
    else:
        print("\nSlow event loop callbacks: (none above threshold)")

    print("=== END RUNTIME PROFILE ===\n")
