#!/usr/bin/env python3
"""CI-gate: таблица краула живёт в своём модуле ``core/crawl/models/``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "core" / "crawl" / "models"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = frozenset(
    {
        "crawl_profile.py",
        "crawl_domain.py",
        "crawl_url.py",
        "crawl_job.py",
    }
)


def main() -> int:
    errors: list[str] = []
    if (REPO_ROOT / "core" / "crawl" / "models.py").is_file():
        errors.append("core/crawl/models.py: tables belong in the models package")
    for path in sorted(MODELS.glob("*.py")):
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        rel = path.relative_to(REPO_ROOT).as_posix()
        expected = 1 if path.name in ONE_TABLE else 0
        if count != expected:
            errors.append(f"{rel}: expected {expected} PlatformModel, found {count}")
    if errors:
        print("check_crawl_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_crawl_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
