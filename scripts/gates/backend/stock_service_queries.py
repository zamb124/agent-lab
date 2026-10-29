#!/usr/bin/env python3
"""CI-gate: сервисы склада без SQL. Одна таблица на файл — scripts/gates/backend/model_files.py."""

from __future__ import annotations

import re
import sys

from scripts.gates.kit import REPO_ROOT

SERVICES = REPO_ROOT / "apps" / "stock" / "services"
FORBIDDEN = re.compile(r"\.objects\.|execute_raw\(|\batomic\(")


def main() -> int:
    errors: list[str] = []
    for path in sorted(SERVICES.glob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                rel = path.relative_to(REPO_ROOT).as_posix()
                errors.append(f"{rel}:{line_no}: query belongs on the model")
    if errors:
        print("check_stock_service_queries: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_stock_service_queries: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
