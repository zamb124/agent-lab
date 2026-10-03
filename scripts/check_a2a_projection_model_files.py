#!/usr/bin/env python3
"""CI-gate: таблица проекции A2A живёт в своём модуле."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "apps" / "flows" / "src" / "models" / "a2a_projection"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = frozenset(
    {
        "task_projection.py",
        "task_message.py",
        "artifact_projection.py",
        "task_event.py",
    }
)


def main() -> int:
    errors: list[str] = []
    legacy = REPO_ROOT / "apps" / "flows" / "src" / "models" / "a2a_projection.py"
    if legacy.is_file():
        errors.append("apps/flows/src/models/a2a_projection.py: tables belong in the package")
    for path in sorted(MODELS.glob("*.py")):
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        rel = path.relative_to(REPO_ROOT).as_posix()
        expected = 1 if path.name in ONE_TABLE else 0
        if count != expected:
            errors.append(f"{rel}: expected {expected} PlatformModel, found {count}")
    if errors:
        print("check_a2a_projection_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_a2a_projection_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
