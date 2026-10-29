"""Корень репозитория и единый отчёт нарушений гейта."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def report(name: str, errors: list[str]) -> int:
    if errors:
        print(f"{name}: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print(f"{name}: OK")
    return 0
