#!/usr/bin/env python3
"""CI-gate: подтверждение upload Sync зовёт FilesService, а не FileRecord."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
OP = "op_files_upload_completed"
FORBIDDEN = ("FileRecord", "stored_file_ref")


def main() -> int:
    source_text = OPERATIONS.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    errors: list[str] = []
    found = False
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != OP:
            continue
        found = True
        source = ast.get_source_segment(source_text, node)
        if source is None:
            errors.append(f"{OP}: source missing")
            break
        if "files_service" not in source:
            errors.append(f"{OP}: must call files_service")
        for name in FORBIDDEN:
            if re.search(rf"\b{name}\b", source):
                errors.append(f"{OP}: {name} belongs in FilesService")
    if not found:
        errors.append(f"{OP}: missing")
    if errors:
        print("check_sync_file_upload_op: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_file_upload_op: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
