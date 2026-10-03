#!/usr/bin/env python3
"""CI-gate: ``op_channels_*`` зовёт ``SyncChannelService``, а не модели."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
FORBIDDEN = ("SyncChannel", "SyncChannelMember", "SyncMessage", "SyncThread")


def main() -> int:
    tree = ast.parse(OPERATIONS.read_text(encoding="utf-8"))
    errors: list[str] = []
    found = 0
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or not node.name.startswith("op_channels_"):
            continue
        found += 1
        source = ast.get_source_segment(OPERATIONS.read_text(encoding="utf-8"), node)
        if source is None:
            errors.append(f"{node.name}: source missing")
            continue
        if "channel_service" not in source:
            errors.append(f"{node.name}: must call channel_service")
        for name in FORBIDDEN:
            if name in source:
                errors.append(f"{node.name}: model call {name} belongs in SyncChannelService")
    if found == 0:
        errors.append("op_channels_*: no channel operations found")
    if errors:
        print("check_sync_channel_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_channel_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
