"""Догоняет собранные, но не сыгранные тесты фазы 1 (обрыв сессии/краш воркера).

``pytest_lastfailed`` покрывает только упавшие. INTERNALERROR планировщика
xdist или SIGKILL воркера обрывает сессию: nodeids, которые не дошли до
исполнения, не попадают ни в junit, ни в lastfailed — без этого скрипта
они теряются молча. Скрипт вычитает исполненные из junit фазы 1 и прогоняет
остаток обычной xdist-командой.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
from pathlib import Path

from scripts.testing.pytest_with_timeout import kill_process_group
from scripts.testing.pytest_workers_profile import (
    junit_executed_nodeids,
    load_collected_nodeids,
)

_CHUNK_NODEIDS = 1500


def _run_pytest(nodeids: list[str], pytest_args: list[str], timeout: float) -> int:
    command = ["uv", "run", "pytest", *nodeids, *pytest_args]
    child_env = dict(os.environ)
    child_env.setdefault("LOGGING__LEVEL", "WARNING")
    # start_new_session как в pytest_with_timeout: killpg снимает uv+pytest+xdist
    # целиком; SIGINT/SIGTERM до detached child иначе не доходят.
    proc = subprocess.Popen(command, env=child_env, start_new_session=True)

    def _on_sigterm(signum: int, _frame: object) -> None:
        kill_process_group(proc)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_process_group(proc)
        return 124


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run collected nodeids that never executed in phase 1.",
    )
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    if not args.junit.is_file():
        print(f"pytest_notrun: junit отсутствует ({args.junit}) — пропуск.")
        return 0
    collected = load_collected_nodeids(junit_mtime=args.junit.stat().st_mtime)
    if collected is None:
        print("pytest_notrun: снимок collected отсутствует или устарел — пропуск.")
        return 0
    missing = sorted(set(collected) - junit_executed_nodeids(args.junit))
    if not missing:
        print("pytest_notrun: все собранные тесты сыграны.")
        return 0

    print(f"pytest_notrun: {len(missing)} не сыгранных тестов из {len(collected)}")
    exit_code = 0
    for offset in range(0, len(missing), _CHUNK_NODEIDS):
        chunk = missing[offset : offset + _CHUNK_NODEIDS]
        result = _run_pytest(chunk, pytest_args, args.timeout)
        if result != 0:
            exit_code = result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
