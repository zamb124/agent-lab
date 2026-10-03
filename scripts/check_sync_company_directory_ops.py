#!/usr/bin/env python3
"""CI-gate: участники компании и общие каналы зовут SyncChannelService."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
OPS = ("op_company_members_list", "op_company_shared_channels_list")
FORBIDDEN = ("Company", "SyncChannel", "SyncMessage", "User.get")


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
        if "channel_service" not in source:
            errors.append(f"{node.name}: must call channel_service")
        for name in FORBIDDEN:
            if re.search(rf"\b{name}\b", source):
                errors.append(f"{node.name}: {name} belongs in SyncChannelService")
    if found != len(OPS):
        errors.append(f"directory ops: expected {len(OPS)}, found {found}")
    if errors:
        print("check_sync_company_directory_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_company_directory_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
