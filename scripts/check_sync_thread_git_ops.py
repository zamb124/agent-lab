#!/usr/bin/env python3
"""CI-gate: треды и Git-ссылки Sync зовут сервис, а не модели из op_* и handlers."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
HANDLERS = REPO_ROOT / "apps" / "sync" / "realtime" / "handlers.py"
OPS = {
    "op_threads_": ("thread_service", ("SyncThread", "SyncMessage")),
    "op_git_resources_": ("git_service", ("GitResourceRef",)),
}
HANDLER_FORBIDDEN = {"create_thread", "upsert_git_resource"}


def main() -> int:
    source_text = OPERATIONS.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    errors: list[str] = []
    found = {prefix: 0 for prefix in OPS}
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        matched = next((prefix for prefix in OPS if node.name.startswith(prefix)), None)
        if matched is None:
            continue
        found[matched] += 1
        source = ast.get_source_segment(source_text, node)
        if source is None:
            errors.append(f"{node.name}: source missing")
            continue
        service_name, forbidden = OPS[matched]
        if service_name not in source:
            errors.append(f"{node.name}: must call {service_name}")
        for name in forbidden:
            if re.search(rf"\b{name}\b", source):
                errors.append(f"{node.name}: model call {name} belongs in the service")
    for prefix, count in found.items():
        if count == 0:
            errors.append(f"{prefix}*: no operations found")
    handler_tree = ast.parse(HANDLERS.read_text(encoding="utf-8"))
    handler_names = {
        node.name
        for node in handler_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in sorted(HANDLER_FORBIDDEN & handler_names):
        errors.append(f"handlers.py: {name} belongs in a service")
    if errors:
        print("check_sync_thread_git_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_thread_git_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
