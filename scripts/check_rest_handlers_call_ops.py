#!/usr/bin/env python3
"""
CI-gate: REST-хендлер сервиса из COMMAND_WS_SERVICES — тонкое зеркало `op_*`.

Каждый `@router.<method>(...)` в `apps/<svc>/api/**` (и `apps/flows/src/api/**`)
обязан вызывать `op_<entity>_<verb>` из каталога. Хендлеры без `op_*` —
протокольные исключения (upload/download байт, A2A, LSP, viewer stream, webhooks)
и долг из `scripts/rest_handlers_without_op_baseline.json` (ratchet: новый
хендлер без `op_*` — FAIL, исчезнувший из долга обязан быть удалён из baseline).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "scripts" / "rest_handlers_without_op_baseline.json"
COMMAND_WS_SERVICES: tuple[str, ...] = ("sync", "worktracker", "wiki", "rag", "office", "crm", "flows", "search")
HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete", "websocket", "api_route"})


def _api_roots(service: str) -> list[Path]:
    return [p for p in (APPS_ROOT / service / "api", APPS_ROOT / service / "src" / "api") if p.is_dir()]


def _is_route_decorator(decorator: ast.expr) -> bool:
    call = decorator if isinstance(decorator, ast.Call) else None
    target = call.func if call is not None else decorator
    return isinstance(target, ast.Attribute) and target.attr in HTTP_METHODS


def _calls_operation(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else callee.attr if isinstance(callee, ast.Attribute) else ""
        if name.startswith("op_"):
            return True
    return False


def collect_handlers_without_op() -> set[str]:
    offenders: set[str] = set()
    for service in COMMAND_WS_SERVICES:
        for api_root in _api_roots(service):
            for path in sorted(api_root.rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                        continue
                    if not any(_is_route_decorator(d) for d in node.decorator_list):
                        continue
                    if _calls_operation(node):
                        continue
                    offenders.add(f"{path.relative_to(REPO_ROOT).as_posix()}::{node.name}")
    return offenders


def main() -> int:
    offenders = collect_handlers_without_op()
    baseline_raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(baseline_raw, list) or not all(isinstance(item, str) for item in baseline_raw):
        raise SystemExit(f"{BASELINE_PATH}: ожидается JSON-массив строк")
    baseline = set(baseline_raw)
    introduced = sorted(offenders - baseline)
    stale = sorted(baseline - offenders)
    if introduced:
        print("check_rest_handlers_call_ops: FAIL — REST-хендлеры без op_* (добавь op_* в каталог сервиса):")
        for item in introduced:
            print(f"  {item}")
    if stale:
        print("check_rest_handlers_call_ops: FAIL — записи baseline больше не актуальны, удали их:")
        for item in stale:
            print(f"  {item}")
    if introduced or stale:
        return 1
    print(f"check_rest_handlers_call_ops: OK (долг: {len(baseline)} хендлеров)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
