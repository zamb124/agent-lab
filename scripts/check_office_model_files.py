#!/usr/bin/env python3
"""CI-gate: таблицы Documents лежат в ``apps/office/models/``, не в ``db/``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "apps" / "office" / "models"
DB = REPO_ROOT / "apps" / "office" / "db"
PATTERN = re.compile(r"is_table:\s*bool\s*=\s*True")
ONE_TABLE = frozenset({"event.py", "link.py", "revision.py"})


def main() -> int:
    errors: list[str] = []
    if DB.exists():
        errors.append("apps/office/db: catalog is forbidden")
    for path in sorted(MODELS.glob("*.py")):
        if path.name == "__init__.py" or path.name == "api.py":
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        rel = path.relative_to(REPO_ROOT).as_posix()
        expected = 1 if path.name in ONE_TABLE else 0
        if count != expected:
            errors.append(f"{rel}: expected {expected} table, found {count}")
    if errors:
        print("check_office_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_office_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
