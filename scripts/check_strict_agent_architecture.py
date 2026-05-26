#!/usr/bin/env python3
"""Strict gates for the agent/flows architecture contract.

This check protects the strict-state refactor from reintroducing removed
contracts, runtime bypasses and untyped compatibility paths in the agent
runtime surface.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

TEXT_SCAN_PATHS: tuple[str, ...] = (
    "apps/flows/src",
    "apps/flows/tools",
    "apps/flows/bundles",
    "core/integrations/mcp.py",
    "core/reflection.py",
    "tests/flows",
)

PYTHON_STRICT_PATHS: tuple[str, ...] = (
    "apps/flows/src",
    "apps/flows/tools",
    "core/integrations/mcp.py",
    "core/reflection.py",
    "core/state/execution_state.py",
)

FLOW_FROM_CONFIG_PATHS: tuple[str, ...] = (
    "apps/flows/src",
    "tests/flows",
)

JSON_BUNDLE_ROOT = "apps/flows/bundles"

UI_REFLECTION_CONTRACTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("apps/flows/src/api/v1/metadata.py", ('"type": "reflection"',)),
    ("apps/flows/ui/constants/node-icons.js", ("reflection:",)),
    (
        "apps/flows/ui/components/editor/flows-node-editor-surface.js",
        ("flows-reflection-node-editor.js", "case 'reflection':"),
    ),
    ("apps/flows/ui/index.js", ("flows-reflection-node-editor.js",)),
    ("apps/flows/ui/_helpers/lara-node-helper.js", ("reflection: 'reflection_node_helper'",)),
    ("core/i18n/translations/en/flows.json", ('"reflection_node_editor"',)),
    ("core/i18n/translations/ru/flows.json", ('"reflection_node_editor"',)),
)

UI_OBSERVABILITY_CONTRACTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "apps/flows/ui/events/resources/logs.resource.js",
        (
            "logsByRequestOp",
            "logsBySpanOp",
            "logsByUserOp",
            "/observability/logs/by-request/",
            "/observability/logs/by-span/",
            "/observability/logs/by-user/",
        ),
    ),
    (
        "apps/flows/ui/app/flows-app.js",
        ("logsByRequestOp", "logsBySpanOp", "logsByUserOp"),
    ),
    (
        "apps/flows/ui/modals/flows-logs-modal.js",
        ("requestId", "spanId", "userId", "logs_by_request", "logs_by_span", "logs_by_user"),
    ),
    (
        "apps/flows/ui/modals/flows-span-details-modal.js",
        ("openModal('flows.logs'", "spanId"),
    ),
)

UI_DURABLE_HISTORY_CONTRACTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "apps/flows/ui/events/resources/durable-history.resource.js",
        (
            "durableHistoryOp",
            "durableBranchesOp",
            "durableStateAtOp",
            "durableForkOp",
            "durableRewindOp",
            "durableRetryFromFailureOp",
            "durableManualPatchOp",
            "/flows/api/v1/tasks/{session_id}/history",
            "/flows/api/v1/tasks/{session_id}/state-at/{sequence}",
            "/flows/api/v1/tasks/{session_id}/retry-from-failure",
            "/flows/api/v1/tasks/{session_id}/manual-patch",
        ),
    ),
    (
        "apps/flows/ui/app/flows-app.js",
        (
            "durableHistoryOp",
            "durableBranchesOp",
            "durableStateAtOp",
            "durableForkOp",
            "durableRewindOp",
            "durableRetryFromFailureOp",
            "durableManualPatchOp",
        ),
    ),
    (
        "apps/flows/ui/modals/flows-durable-history-modal.js",
        (
            "flows.durable_history",
            "durable_history_modal.timeline_title",
            "flows/durable_history",
            "flows/durable_fork",
            "flows/durable_rewind",
            "flows/durable_retry_from_failure",
            "flows/durable_manual_patch",
            "durable_history_modal.action_copy_anchor",
            "durable_history_modal.action_patch",
        ),
    ),
    ("apps/flows/ui/index.js", ("flows-durable-history-modal.js",)),
    (
        "apps/flows/ui/modals/flows-sessions-modal.js",
        ("openModal('flows.durable_history'", "history_aria", "trace-timeline"),
    ),
    (
        "apps/flows/ui/pages/chat-page.js",
        ("openModal('flows.durable_history'", "btn_history", "trace-timeline"),
    ),
    (
        "apps/flows/ui/modals/flows-span-details-modal.js",
        (
            "openModal('flows.durable_history'",
            "platform.workflow.session_id",
            "platform.session.agent",
            "action_durable_history",
        ),
    ),
    (
        "core/i18n/translations/en/flows.json",
        ('"durable_history_modal"', '"btn_history"', '"history_aria"', '"action_patch"'),
    ),
    (
        "core/i18n/translations/ru/flows.json",
        ('"durable_history_modal"', '"btn_history"', '"history_aria"', '"action_patch"'),
    ),
)

NEGATIVE_CONTRACT_TESTS: frozenset[str] = frozenset(
    {
        "tests/flows/core/test_runtime_strictness.py",
    }
)

FORBIDDEN_DELETED_SYMBOLS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bbranch_body\b"), "branch_body wrapper is removed; use BranchCreateRequest/BranchUpdateRequest"),
    (re.compile(r"\bself_check\b"), "self_check tool is removed; use typed ReflectionNode/CriticPolicy"),
    (re.compile(r"\bargs_schema\b"), "args_schema is removed; use parameters_schema"),
    (re.compile(r"\bCallParameter\b"), "CallParameter legacy tool schema is removed"),
    (re.compile(r"\bsimple_executor\b|\bSimpleExecutor\b"), "simple_executor runtime bypass is removed"),
    (re.compile(r"\bdirect[-_ ]runtime\b"), "direct runtime bypass is forbidden"),
    (re.compile(r"\bruntime[-_ ]bypass\b"), "runtime bypass is forbidden"),
)

RAW_AGENT_TRACE_ATTRIBUTE = re.compile(
    r"""["']platform\.(workflow|hitl|memory|reflection|mcp)\.""",
)


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    message: str

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT).as_posix()
        return f"{rel}:{self.lineno}: {self.message}"


def _path_candidates(entries: Iterable[str]) -> list[Path]:
    candidates: list[Path] = []
    for entry in entries:
        path = REPO_ROOT / entry
        if path.exists():
            candidates.append(path)
    return candidates


def _iter_files(entries: Iterable[str], suffixes: tuple[str, ...]) -> Iterable[Path]:
    for path in _path_candidates(entries):
        if path.is_file():
            if path.suffix in suffixes:
                yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix in suffixes:
                rel_parts = child.relative_to(REPO_ROOT).parts
                if "__pycache__" not in rel_parts:
                    yield child


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _scan_deleted_symbols() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_files(TEXT_SCAN_PATHS, (".py", ".json")):
        text = path.read_text(encoding="utf-8")
        for pattern, message in FORBIDDEN_DELETED_SYMBOLS:
            for match in pattern.finditer(text):
                violations.append(
                    Violation(
                        path=path,
                        lineno=_line_number(text, match.start()),
                        message=message,
                    )
                )
    return violations


def _is_flow_from_config_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "from_config":
        return False
    return isinstance(func.value, ast.Name) and func.value.id == "Flow"


def _has_non_none_container_keyword(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg != "container":
            continue
        return not (
            isinstance(keyword.value, ast.Constant)
            and keyword.value.value is None
        )
    return False


def _scan_flow_from_config_contract() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_files(FLOW_FROM_CONFIG_PATHS, (".py",)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in NEGATIVE_CONTRACT_TESTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_flow_from_config_call(node):
                if not _has_non_none_container_keyword(node):
                    violations.append(
                        Violation(
                            path=path,
                            lineno=node.lineno,
                            message="Flow.from_config must pass a non-None runtime container",
                        )
                    )
    return violations


def _scan_getattr_defaults() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_files(PYTHON_STRICT_PATHS, (".py",)):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
                continue
            if len(node.args) >= 3:
                violations.append(
                    Violation(
                        path=path,
                        lineno=node.lineno,
                        message="getattr(..., default) is forbidden in strict agent runtime surface",
                    )
                )
    return violations


def _scan_raw_agent_trace_attribute_literals() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_files(PYTHON_STRICT_PATHS, (".py",)):
        text = path.read_text(encoding="utf-8")
        for match in RAW_AGENT_TRACE_ATTRIBUTE.finditer(text):
            violations.append(
                Violation(
                    path=path,
                    lineno=_line_number(text, match.start()),
                    message=(
                        "agent trace attributes must use constants from "
                        "core.tracing.attributes"
                    ),
                )
            )
    return violations


def _walk_json_edges(path: Path, value: object, pointer: str) -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(value, dict):
        edges = value.get("edges")
        if isinstance(edges, list):
            for index, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    continue
                for key in ("from", "to"):
                    if key in edge:
                        violations.append(
                            Violation(
                                path=path,
                                lineno=1,
                                message=(
                                    f"{pointer}/edges/{index}: legacy edge key {key!r} "
                                    "is forbidden; use from_node/to_node"
                                ),
                            )
                        )
        for key, child in value.items():
            violations.extend(_walk_json_edges(path, child, f"{pointer}/{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_walk_json_edges(path, child, f"{pointer}/{index}"))
    return violations


def _scan_bundle_edge_contracts() -> list[Violation]:
    root = REPO_ROOT / JSON_BUNDLE_ROOT
    if not root.exists():
        return []
    violations: list[Violation] = []
    for path in root.rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        violations.extend(_walk_json_edges(path, value, ""))
    return violations


def _scan_required_text_contracts(
    contracts: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    message_prefix: str,
) -> list[Violation]:
    violations: list[Violation] = []
    for rel_path, required_tokens in contracts:
        path = REPO_ROOT / rel_path
        if not path.exists():
            violations.append(
                Violation(
                    path=path,
                    lineno=1,
                    message=f"{message_prefix}: required file is missing",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        for token in required_tokens:
            if token not in text:
                violations.append(
                    Violation(
                        path=path,
                        lineno=1,
                        message=f"{message_prefix}: missing token {token!r}",
                    )
                )
    return violations


def _scan_observability_ui_contracts() -> list[Violation]:
    violations = _scan_required_text_contracts(
        UI_OBSERVABILITY_CONTRACTS,
        message_prefix="observability UI contract",
    )
    logs_modal = REPO_ROOT / "apps/flows/ui/modals/flows-logs-modal.js"
    if logs_modal.exists():
        text = logs_modal.read_text(encoding="utf-8")
        for match in re.finditer(r"\bfallback\b", text, flags=re.IGNORECASE):
            violations.append(
                Violation(
                    path=logs_modal,
                    lineno=_line_number(text, match.start()),
                    message="observability UI must resolve trace_id through explicit props or Tempo APIs, not fallback heuristics",
                )
            )
    return violations


def _scan_reflection_ui_contracts() -> list[Violation]:
    return _scan_required_text_contracts(
        UI_REFLECTION_CONTRACTS,
        message_prefix="ReflectionNode UI contract",
    )


def _scan_durable_history_ui_contracts() -> list[Violation]:
    violations = _scan_required_text_contracts(
        UI_DURABLE_HISTORY_CONTRACTS,
        message_prefix="durable history UI contract",
    )
    durable_modal = REPO_ROOT / "apps/flows/ui/modals/flows-durable-history-modal.js"
    if durable_modal.exists():
        text = durable_modal.read_text(encoding="utf-8")
        for match in re.finditer(r"\bfallback\b", text, flags=re.IGNORECASE):
            violations.append(
                Violation(
                    path=durable_modal,
                    lineno=_line_number(text, match.start()),
                    message="durable history UI must use typed tasks API shapes, not compatibility fallbacks",
                )
            )
    return violations


def collect_violations() -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(_scan_deleted_symbols())
    violations.extend(_scan_flow_from_config_contract())
    violations.extend(_scan_getattr_defaults())
    violations.extend(_scan_raw_agent_trace_attribute_literals())
    violations.extend(_scan_bundle_edge_contracts())
    violations.extend(_scan_reflection_ui_contracts())
    violations.extend(_scan_observability_ui_contracts())
    violations.extend(_scan_durable_history_ui_contracts())
    return sorted(violations, key=lambda item: (item.path.as_posix(), item.lineno, item.message))


def main() -> int:
    violations = collect_violations()
    if not violations:
        print("check_strict_agent_architecture: OK")
        return 0

    print("check_strict_agent_architecture: FAIL", file=sys.stderr)
    for violation in violations:
        print(violation.format(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
