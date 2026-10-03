#!/usr/bin/env python3
"""CI-gate: ``op_messages_*`` зовёт ``SyncMessageService``, а не модели."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
FORBIDDEN = ("SyncMessage", "SyncMessageContent", "SyncThread", "SyncChannel", "SyncCall")


def main() -> int:
    source_text = OPERATIONS.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    errors: list[str] = []
    found = 0
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or not node.name.startswith("op_messages_"):
            continue
        found += 1
        source = ast.get_source_segment(source_text, node)
        if source is None:
            errors.append(f"{node.name}: source missing")
            continue
        if "message_service" not in source:
            errors.append(f"{node.name}: must call message_service")
        for name in FORBIDDEN:
            if name in source:
                errors.append(f"{node.name}: model call {name} belongs in SyncMessageService")
    if found == 0:
        errors.append("op_messages_*: no message operations found")
    if errors:
        print("check_sync_message_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_message_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
