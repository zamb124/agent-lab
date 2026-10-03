#!/usr/bin/env python3
"""CI-gate: сервисы склада без SQL; одна таблица — один модуль моделей."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES = REPO_ROOT / "apps" / "stock" / "services"
FORBIDDEN = re.compile(r"\.objects\.|execute_raw\(|\batomic\(")


def _model_class_counts() -> list[str]:
    import re

    pattern = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
    errors: list[str] = []
    models = REPO_ROOT / "apps" / "stock" / "models"
    for path in sorted(models.glob("*.py")):
        if path.name in {"__init__.py", "enums.py", "common.py", "api.py", "valuation.py", "events.py", "gs1.py", "storage_rules.py", "removal.py", "scan.py"}:
            continue
        count = len(pattern.findall(path.read_text(encoding="utf-8")))
        if count != 1:
            rel = path.relative_to(REPO_ROOT).as_posix()
            errors.append(f"{rel}: expected one PlatformModel, found {count}")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_model_class_counts())
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
