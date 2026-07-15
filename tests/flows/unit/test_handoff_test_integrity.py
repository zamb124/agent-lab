from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_test_doubles]

_ROOT = Path(__file__).resolve().parents[3]
_STRICT_HANDOFF_SUITES = (
    _ROOT / "tests/flows/integration/test_flow_tool_handoff_kernel.py",
    _ROOT / "tests/flows/api/test_flow_tool_call_type.py",
    _ROOT / "tests/flows/unit/test_flow_tool_reference.py",
    _ROOT / "tests/flows/services/test_handoff_orchestrator_schema.py",
    _ROOT / "tests/flows/unit/test_message_author.py",
)
_FORBIDDEN_IMPORT_PREFIXES = ("unittest.mock", "pytest_mock")
_FORBIDDEN_SYMBOLS = {
    "asyncmock",
    "magicmock",
    "mock",
    "mocker",
    "monkeypatch",
    "patch",
    "setup_mock_responses",
}


def _suite_id(path: Path) -> str:
    return path.name


@pytest.mark.parametrize("suite", _STRICT_HANDOFF_SUITES, ids=_suite_id)
def test_strict_handoff_suite_contains_no_test_double_hooks(suite: Path) -> None:
    source = suite.read_text(encoding="utf-8")
    assert "pytest.mark.no_test_doubles" in source, (
        f"{suite.name} must disable autouse test doubles"
    )
    tree = ast.parse(source, filename=str(suite))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"line {node.lineno}: from {module} import ...")
            for alias in node.names:
                if alias.name.casefold() in _FORBIDDEN_SYMBOLS:
                    violations.append(f"line {node.lineno}: imported symbol {alias.name}")
        elif isinstance(node, ast.Name) and node.id.casefold() in _FORBIDDEN_SYMBOLS:
            violations.append(f"line {node.lineno}: symbol {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.casefold() in _FORBIDDEN_SYMBOLS:
            violations.append(f"line {node.lineno}: attribute {node.attr}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                if argument.arg.casefold() in _FORBIDDEN_SYMBOLS:
                    violations.append(f"line {node.lineno}: fixture/argument {argument.arg}")

    assert violations == [], f"{suite.name} must use real handoff components: {violations}"
