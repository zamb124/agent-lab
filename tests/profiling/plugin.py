from __future__ import annotations

import glob
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


def pytest_configure(config: pytest.Config) -> None:
    if not profiling_enabled():
        return
    for stale_report in glob.glob("/tmp/platform_test_runtime_profile_*.json"):
        Path(stale_report).unlink(missing_ok=True)
    install_filelock_patch()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, object, object]:
    if profiling_enabled():
        get_collector().set_current_test(item.nodeid)
    yield


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
