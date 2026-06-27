#!/usr/bin/env python3
"""Запрещает monkeypatch/patch в HumanitecAgent E2E (real stack only)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = (
    REPO_ROOT / "tests/agent/e2e",
    REPO_ROOT / "tests/agent/desktop_e2e",
)

FORBIDDEN_IMPORT_MODULES = frozenset({"unittest.mock", "mock"})
FORBIDDEN_IMPORT_NAMES = frozenset({"patch", "MagicMock", "AsyncMock", "Mock"})
FORBIDDEN_NAMES = frozenset({"monkeypatch", "MagicMock", "AsyncMock"})


class _ForbiddenVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.mock_patch_imported = False
        self.violations: list[str] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module
        if module in FORBIDDEN_IMPORT_MODULES:
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORT_NAMES:
                    if alias.name == "patch":
                        self.mock_patch_imported = True
                    self.violations.append(
                        f"{self.path.relative_to(REPO_ROOT)}:{node.lineno}: import {alias.name} from {module}"
                    )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.violations.append(f"{self.path.relative_to(REPO_ROOT)}:{node.lineno}: {node.id}")
        if self.mock_patch_imported and node.id == "patch":
            self.violations.append(f"{self.path.relative_to(REPO_ROOT)}:{node.lineno}: patch")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_NAMES:
            self.violations.append(f"{self.path.relative_to(REPO_ROOT)}:{node.lineno}: {node.attr}")
        self.generic_visit(node)


def main() -> int:
    violations: list[str] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for path in sorted(scan_dir.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            visitor = _ForbiddenVisitor(path)
            visitor.visit(tree)
            violations.extend(visitor.violations)
    if violations:
        print("check_agent_test_no_monkeypatch: forbidden mocks in agent E2E:", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_agent_test_no_monkeypatch: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
