#!/usr/bin/env python3
"""CI-gate: коннектор и подключение datasource — разные модули."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "core" / "datasources" / "models"
LEGACY = REPO_ROOT / "core" / "datasources" / "models.py"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = {"connector_spec.py": 1, "connection.py": 1}
ZERO = {"__init__.py", "contracts.py"}


def main() -> int:
    errors: list[str] = []
    if LEGACY.exists():
        errors.append("core/datasources/models.py: file remains")
    if not PACKAGE.is_dir():
        errors.append("core/datasources/models: missing package")
    else:
        for name, expected in ONE_TABLE.items():
            path = PACKAGE / name
            count = len(PATTERN.findall(path.read_text(encoding="utf-8"))) if path.is_file() else -1
            if count != expected:
                errors.append(f"{name}: expected {expected} PlatformModel, found {count}")
        for name in ZERO:
            path = PACKAGE / name
            if not path.is_file():
                errors.append(f"{name}: missing")
                continue
            count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
            if count != 0:
                errors.append(f"{name}: expected 0 PlatformModel, found {count}")
    if errors:
        print("check_datasource_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_datasource_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
