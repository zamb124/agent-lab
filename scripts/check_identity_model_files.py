#!/usr/bin/env python3
"""CI-gate: таблица идентичности живёт в своём модуле ``core/models/identity_models/``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "core" / "models" / "identity_models"
PATTERN = re.compile(r"is_table:\s*bool\s*=\s*True")
ONE_TABLE = frozenset(
    {
        "user.py",
        "company.py",
        "auth_session.py",
        "user_provider_record.py",
        "namespace.py",
    }
)


def main() -> int:
    errors: list[str] = []
    if (REPO_ROOT / "core" / "models" / "identity_models.py").is_file():
        errors.append("core/models/identity_models.py: tables belong in the package")
    for path in sorted(MODELS.glob("*.py")):
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        rel = path.relative_to(REPO_ROOT).as_posix()
        expected = 1 if path.name in ONE_TABLE else 0
        if count != expected:
            errors.append(f"{rel}: expected {expected} table, found {count}")
    if errors:
        print("check_identity_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_identity_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
