#!/usr/bin/env python3
"""
CI-gate: деньги проходят только через billing spans.

1. `record_usage(` вызывается только внутри `core/billing/service.py` (settlement job).
2. Каждый `traced_operation(...)` с `billing_pending_settlement=True` и литеральным
   `operation_name` покрыт правилом из `core/billing/default_settlement_rules.py`
   (`operation_name_prefix` / `operation_name_equals`); operation_name с f-строкой
   проверяется по литеральному префиксу до первой `{`.
3. `require_balance_for_billable_operation` и `record_llm_response` — только в
   allowlist (LLMClient, billing, speech/embedding/rerank/livekit/guest/search).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT

SCAN_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "core")
SETTLEMENT_ALLOWED_FILE = REPO_ROOT / "core" / "billing" / "service.py"
RULES_PATH = REPO_ROOT / "core" / "billing" / "default_settlement_rules.py"
SKIP_PARTS: frozenset[str] = frozenset({"vendor", "__pycache__", "desktop"})
REQUIRE_BALANCE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/clients/llm/billing.py",
        "core/ai/embedding_client.py",
        "apps/sync/services/livekit_client.py",
        "apps/guest_runtime/services/farm_service.py",
        "apps/search/services/meta.py",
        "apps/voice/api/session.py",
    }
)
RECORD_LLM_RESPONSE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/clients/llm/billing.py",
    }
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            files.append(path)
    return files


def _rule_matchers() -> tuple[list[str], set[str]]:
    tree = ast.parse(RULES_PATH.read_text(encoding="utf-8"), filename=str(RULES_PATH))
    prefixes: list[str] = []
    exact: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (isinstance(callee, ast.Name) and callee.id == "SettlementRuleMatch"):
            continue
        for keyword in node.keywords:
            if not isinstance(keyword.value, ast.Constant) or not isinstance(keyword.value.value, str):
                continue
            if keyword.arg == "operation_name_prefix":
                prefixes.append(keyword.value.value)
            elif keyword.arg == "operation_name_equals":
                exact.add(keyword.value.value)
    if not prefixes and not exact:
        raise SystemExit(f"{RULES_PATH}: не найдено ни одного SettlementRuleMatch с operation_name")
    return prefixes, exact


def _operation_name_literals(node: ast.expr, function: ast.AsyncFunctionDef | ast.FunctionDef | None) -> list[str] | None:
    """Литеральные значения operation_name: константа, литеральный префикс f-строки
    или параметр функции, аннотированный `Literal[...]` из строк."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        first = node.values[0] if node.values else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return [first.value]
        return [""]
    if isinstance(node, ast.Name) and function is not None:
        for arg in [*function.args.args, *function.args.kwonlyargs]:
            if arg.arg != node.id or arg.annotation is None:
                continue
            annotation = arg.annotation
            if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name) and annotation.value.id == "Literal":
                values = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
                literals = [v.value for v in values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                if literals:
                    return literals
    return None


def _enclosing_function(tree: ast.AST) -> dict[int, ast.AsyncFunctionDef | ast.FunctionDef]:
    by_call_line: dict[int, ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    by_call_line.setdefault(inner.lineno, node)
    return by_call_line


def _covered(operation_name: str, prefixes: list[str], exact: set[str]) -> bool:
    if operation_name in exact:
        return True
    return any(operation_name.startswith(prefix) or prefix.startswith(operation_name) for prefix in prefixes if operation_name)


def main() -> int:
    prefixes, exact = _rule_matchers()
    errors: list[str] = []
    pending_sites = 0
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(REPO_ROOT).as_posix()
        functions_by_line = _enclosing_function(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else callee.attr if isinstance(callee, ast.Attribute) else ""
            if name == "record_usage" and path != SETTLEMENT_ALLOWED_FILE:
                errors.append(f"{rel}:{node.lineno}: прямой record_usage — деньги идут только через billing span + settlement")
            if name == "require_balance_for_billable_operation" and rel not in REQUIRE_BALANCE_ALLOWLIST:
                errors.append(
                    f"{rel}:{node.lineno}: require_balance_for_billable_operation вне allowlist "
                    + "(LLM — core/clients/llm/billing.py; остальные — speech/embedding/livekit/guest/search)"
                )
            if name == "record_llm_response" and rel not in RECORD_LLM_RESPONSE_ALLOWLIST:
                errors.append(
                    f"{rel}:{node.lineno}: record_llm_response вне allowlist — только core/clients/llm/billing.py"
                )
            if name != "traced_operation":
                continue
            pending = any(
                keyword.arg == "billing_pending_settlement"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if not pending:
                continue
            pending_sites += 1
            if not node.args:
                errors.append(f"{rel}:{node.lineno}: traced_operation без operation_name")
                continue
            operation_names = _operation_name_literals(node.args[0], functions_by_line.get(node.lineno))
            if operation_names is None:
                errors.append(f"{rel}:{node.lineno}: operation_name span с pending_settlement должен быть литералом, f-строкой с литеральным префиксом или Literal-параметром")
                continue
            for operation_name in operation_names:
                if not _covered(operation_name, prefixes, exact):
                    errors.append(
                        f"{rel}:{node.lineno}: span {operation_name!r} с pending_settlement не покрыт правилом default_settlement_rules"
                    )
    if errors:
        print("check_billing_span_canon: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"check_billing_span_canon: OK ({pending_sites} pending-spans, {len(prefixes) + len(exact)} правил)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
