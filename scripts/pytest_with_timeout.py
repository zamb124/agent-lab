"""Запуск pytest с wall-clock таймаутом; при превышении — exit 124."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: pytest_with_timeout.py <timeout_seconds> <command...>",
            file=sys.stderr,
        )
        return 2
    timeout_seconds = float(sys.argv[1])
    command = sys.argv[2:]
    try:
        completed = subprocess.run(command, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        print(
            f"pytest timed out after {timeout_seconds:g} seconds: {' '.join(command)}",
            file=sys.stderr,
        )
        return 124
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
