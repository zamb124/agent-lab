#!/usr/bin/env python3
"""CI-gate: у процесса нет apps/<process>/components.py; recipes живут в di.py."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS = REPO_ROOT / "apps"


def main() -> int:
    found = sorted(path.relative_to(REPO_ROOT).as_posix() for path in APPS.glob("*/components.py"))
    if found:
        print("check_no_service_components: FAIL", file=sys.stderr)
        for path in found:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("check_no_service_components: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
