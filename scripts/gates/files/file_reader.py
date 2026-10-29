#!/usr/bin/env python3
"""CI gate: product code uses FileReader.read(ReadFileArgs), not bypass extract pipeline."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as ROOT

SCAN_ROOTS = (
    ROOT / "apps",
    ROOT / "core" / "rag",
)

FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b_get_or_extract\s*\("), "_get_or_extract outside core/files/reader"),
    (re.compile(r"\bbuild_file_extract\s*\("), "build_file_extract outside core/files/reader"),
    (re.compile(r"\.read_raw\s*\("), "read_raw in product layer (use FileReader.read)"),
)

ALLOWLIST_SUFFIXES = (".py",)


def _iter_py_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [path for path in base.rglob("*.py") if path.is_file()]


def main() -> int:
    violations: list[str] = []
    for root in SCAN_ROOTS:
        for path in _iter_py_files(root):
            if not path.name.endswith(ALLOWLIST_SUFFIXES):
                continue
            text = path.read_text(encoding="utf-8")
            for pattern, message in FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    violations.append(f"{path.relative_to(ROOT)}: {message}")

    if violations:
        print("FileReader canon violations:", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("FileReader canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
