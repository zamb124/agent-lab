#!/usr/bin/env python3
"""
Запуск pytest с runtime-профилированием (FileLock + медленные asyncio callback'и).

Примеры:
  uv run python scripts/run_pytest_profile.py tests/sync/api/test_sync_calls_e2e.py -n 5
  uv run python scripts/run_pytest_profile.py tests/ -n 5 -m "not integration" --ignore=tests/ui

Отчёты:
  /tmp/platform_test_runtime_profile_<gw>.json  — per worker
  /tmp/platform_test_runtime_profile_merged.json — сводка (controller)

Пороги (мс):
  PLATFORM_TEST_PROFILE_LOCK_WARN_MS=50   (default)
  PLATFORM_TEST_PROFILE_LOOP_WARN_MS=25    (default)
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2

    env = os.environ.copy()
    env.setdefault("PLATFORM_TEST_PROFILE_RUNTIME", "1")

    command = ["uv", "run", "pytest", *sys.argv[1:]]
    completed = subprocess.run(command, env=env, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
