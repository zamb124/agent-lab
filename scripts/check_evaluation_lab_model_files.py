#!/usr/bin/env python3
"""CI-gate: одна таблица evaluation lab на файл пакета."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "apps" / "flows" / "src" / "models" / "evaluation_lab"
LEGACY = REPO_ROOT / "apps" / "flows" / "src" / "models" / "evaluation_lab.py"
PATTERN = re.compile(r"is_table:\s*bool\s*=\s*True")
EXCEPTIONS = {"__init__.py", "contracts.py"}


def main() -> int:
    errors: list[str] = []
    if LEGACY.exists():
        errors.append("apps/flows/src/models/evaluation_lab.py: file remains")
    if not PACKAGE.is_dir():
        errors.append("apps/flows/src/models/evaluation_lab: missing package")
    else:
        for path in sorted(PACKAGE.glob("*.py")):
            count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
            if path.name in EXCEPTIONS:
                if count != 0:
                    errors.append(f"{path.name}: expected 0 tables, found {count}")
                continue
            if count != 1:
                errors.append(f"{path.name}: expected 1 table, found {count}")
    if errors:
        print("check_evaluation_lab_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_evaluation_lab_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
