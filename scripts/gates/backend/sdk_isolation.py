#!/usr/bin/env python3
"""sdk/ не импортирует apps и core: пакет ставится отдельно от платформы."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report

_SDK = REPO_ROOT / "sdk"
_FORBIDDEN = ("apps", "core")


def _imported_roots(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".", 1)[0]
            if root in _FORBIDDEN:
                found.append((node.lineno, name))
    return found


def main() -> int:
    failures: list[str] = []
    if not _SDK.is_dir():
        failures.append("sdk/ отсутствует")
    else:
        for path in sorted(_SDK.rglob("*.py")):
            for lineno, name in _imported_roots(path):
                rel = path.relative_to(REPO_ROOT).as_posix()
                failures.append(f"{rel}:{lineno} импортирует {name}")
    return report("sdk_isolation", failures)


if __name__ == "__main__":
    sys.exit(main())
