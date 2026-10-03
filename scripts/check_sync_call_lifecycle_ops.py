#!/usr/bin/env python3
"""CI-gate: приглашение, принятие, отказ и выход из звонка зовут SyncCallService."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
OPS = ("op_calls_invite", "op_calls_accept", "op_calls_decline", "op_calls_hangup")
FORBIDDEN = ("handle_call_", "SyncCall", "SyncChannel", "maybe_start_speech_to_chat_poll")


def main() -> int:
    source_text = OPERATIONS.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    errors: list[str] = []
    found = 0
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in OPS:
            continue
        found += 1
        source = ast.get_source_segment(source_text, node)
        if source is None:
            errors.append(f"{node.name}: source missing")
            continue
        if "call_service" not in source:
            errors.append(f"{node.name}: must call call_service")
        for name in FORBIDDEN:
            if name in source:
                errors.append(f"{node.name}: {name} belongs in SyncCallService")
    if found != len(OPS):
        errors.append(f"lifecycle ops: expected {len(OPS)}, found {found}")
    if errors:
        print("check_sync_call_lifecycle_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_call_lifecycle_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
