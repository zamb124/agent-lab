#!/usr/bin/env python3
"""CI-gate: актуальная переменная и её версия — разные модули."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "core" / "secrets" / "models"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = {
    "secret_variable.py": 1,
    "secret_variable_version.py": 1,
    "contracts.py": 0,
    "value.py": 0,
}


def main() -> int:
    errors: list[str] = []
    if (REPO_ROOT / "core" / "secrets" / "models.py").exists():
        errors.append("core/secrets/models.py: package replaced this module")
    for name, expected in ONE_TABLE.items():
        path = MODELS / name
        if not path.is_file():
            errors.append(f"core/secrets/models/{name}: missing")
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        if count != expected:
            errors.append(f"core/secrets/models/{name}: expected {expected} PlatformModel, found {count}")
    if errors:
        print("check_secrets_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_secrets_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
