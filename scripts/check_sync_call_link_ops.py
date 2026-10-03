#!/usr/bin/env python3
"""CI-gate: ссылки на звонок и вход гостя зовут SyncCallLinkService."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
OPS = (
    "op_calls_links_list",
    "op_calls_links_create",
    "op_calls_links_update",
    "op_calls_links_remove",
    "op_calls_join_info",
    "op_calls_join_accept",
)
FORBIDDEN = ("SyncCallLink", "SyncCall", "SyncChannel", "livekit_client")


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
        if "call_link_service" not in source:
            errors.append(f"{node.name}: must call call_link_service")
        for name in FORBIDDEN:
            if name in source:
                errors.append(f"{node.name}: {name} belongs in SyncCallLinkService")
    if found != len(OPS):
        errors.append(f"link ops: expected {len(OPS)}, found {found}")
    if errors:
        print("check_sync_call_link_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_call_link_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
