#!/usr/bin/env python3
"""CI-gate: отправка сообщения Sync живёт в SyncMessageService, не в handlers.py."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDLERS = REPO_ROOT / "apps" / "sync" / "realtime" / "handlers.py"
SERVICE = REPO_ROOT / "apps" / "sync" / "services" / "message_service.py"
FORBIDDEN = {"send_message", "send_message_with_side_effects"}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    errors: list[str] = []
    if not SERVICE.is_file():
        errors.append("apps/sync/services/message_service.py: missing")
    else:
        missing = FORBIDDEN - _function_names(SERVICE)
        for name in sorted(missing):
            errors.append(f"message_service.py: missing {name}")
    if HANDLERS.is_file():
        leaked = FORBIDDEN & _function_names(HANDLERS)
        for name in sorted(leaked):
            errors.append(f"handlers.py: {name} belongs in SyncMessageService")
    else:
        errors.append("apps/sync/realtime/handlers.py: missing")
    if errors:
        print("check_sync_message_send: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_message_send: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
