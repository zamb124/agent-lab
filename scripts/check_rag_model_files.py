#!/usr/bin/env python3
"""CI-gate: статус индексации и чанк RAG — разные модули."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "core" / "db" / "models" / "rag"
PATTERN = re.compile(r"^class \w+\(.*PlatformModel", re.MULTILINE)
ONE_TABLE = {
    "processing_status.py": 1,
    "vector_document.py": 1,
}


def main() -> int:
    errors: list[str] = []
    if (REPO_ROOT / "core" / "db" / "models" / "rag.py").exists():
        errors.append("core/db/models/rag.py: package replaced this module")
    for name, expected in ONE_TABLE.items():
        path = MODELS / name
        if not path.is_file():
            errors.append(f"core/db/models/rag/{name}: missing")
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8")))
        if count != expected:
            errors.append(f"core/db/models/rag/{name}: expected {expected} PlatformModel, found {count}")
    if errors:
        print("check_rag_model_files: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_rag_model_files: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
