#!/usr/bin/env python3
"""CI gate: Documents public id is file_id only (ban legacy placement dual-id tokens)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = re.compile(
    r"(?<![A-Za-z0-9_])binding_id(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])binding_kind(?![A-Za-z0-9_])"
)

SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "apps" / "office",
    REPO_ROOT / "core" / "office",
    REPO_ROOT / "tests" / "office",
    REPO_ROOT / "tests" / "ui" / "e2e",
    REPO_ROOT / ".cursor" / "rules",
)

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".git",
        "dist",
        "build",
        ".venv",
        "versions",
    }
)

ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".js", ".mdc", ".md", ".json", ".sh", ".yml", ".yaml"}
)

# Historical Alembic revisions may still mention binding_id.
SKIP_PATH_PREFIXES: tuple[Path, ...] = (
    REPO_ROOT / "migrations" / "office" / "versions",
)


def _is_skipped(path: Path) -> bool:
    resolved = path.resolve()
    for prefix in SKIP_PATH_PREFIXES:
        try:
            resolved.relative_to(prefix.resolve())
            return True
        except ValueError:
            continue
    if path.name == "check_office_file_id_canon.py":
        return True
    return False


def main() -> int:
    errors: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix not in ALLOWED_SUFFIXES:
                continue
            if _is_skipped(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if FORBIDDEN.search(text) is None:
                continue
            rel = path.relative_to(REPO_ROOT)
            for line_no, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN.search(line) is not None:
                    errors.append(f"{rel}:{line_no}: forbidden binding_id/bindingId/binding_kind")
    if errors:
        print("check_office_file_id_canon: FAIL", file=sys.stderr)
        for err in errors[:200]:
            print(f"  {err}", file=sys.stderr)
        if len(errors) > 200:
            print(f"  ... and {len(errors) - 200} more", file=sys.stderr)
        return 1
    print("check_office_file_id_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
