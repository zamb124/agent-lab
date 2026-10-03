#!/usr/bin/env python3
"""CI-gate: таблица wiki живёт в своём модуле ``apps/wiki/models/``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "apps" / "wiki" / "models"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = frozenset({"page.py", "page_link.py", "revision.py", "comment.py"})
SKIP = frozenset({"__init__.py", "domain.py", "api.py"})


def main() -> int:
    errors: list[str] = []
    for path in sorted(MODELS.glob("*.py")):
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.name in ONE_TABLE and count != 1:
            errors.append(f"{rel}: expected one PlatformModel, found {count}")
        elif path.name not in ONE_TABLE and path.name not in SKIP and count != 0:
            errors.append(f"{rel}: expected no PlatformModel, found {count}")
        elif path.name in SKIP and count != 0:
            errors.append(f"{rel}: table class belongs in its own module, found {count}")
    if errors:
        print("check_wiki_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_wiki_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
