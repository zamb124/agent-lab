#!/usr/bin/env python3
"""CI-gate: шаблон пространства CRM и его тип — разные модули."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "apps" / "crm" / "models"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = {
    "namespace_template.py": 1,
    "namespace_template_type.py": 1,
}


def main() -> int:
    errors: list[str] = []
    for name, expected in ONE_TABLE.items():
        path = MODELS / name
        if not path.is_file():
            errors.append(f"apps/crm/models/{name}: missing")
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        if count != expected:
            errors.append(f"apps/crm/models/{name}: expected {expected} PlatformModel, found {count}")
    if errors:
        print("check_crm_namespace_template_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_crm_namespace_template_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
