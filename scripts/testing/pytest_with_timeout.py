"""Запуск pytest с wall-clock таймаутом; при превышении — kill process group, exit 124.

``subprocess.run(..., timeout=)`` убивает только родителя (``uv``). xdist-воркеры
остаются и продолжают держать стек. Новая сессия + ``killpg`` снимает всё дерево
pytest, granian/test_stack не трогает (другая process group).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys


def kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        _ = proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    _ = proc.wait(timeout=5)


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: pytest_with_timeout.py <timeout_seconds> <command...>",
            file=sys.stderr,
        )
        return 2
    timeout_seconds = float(sys.argv[1])
    command = sys.argv[2:]
    proc = subprocess.Popen(command, start_new_session=True)

    def _on_sigterm(signum: int, _frame: object) -> None:
        # SIGTERM сам по себе killpg не делает: detached child переживает wrapper.
        kill_process_group(proc)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            f"pytest timed out after {timeout_seconds:g} seconds: {' '.join(command)}",
            file=sys.stderr,
        )
        kill_process_group(proc)
        return 124
    except KeyboardInterrupt:
        # start_new_session оторвал дочерний pytest от tty — SIGINT до него не
        # доходит, без killpg он продолжает жить сиротой и печатать в терминал.
        kill_process_group(proc)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
