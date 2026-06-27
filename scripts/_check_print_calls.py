"""
Поиск настоящих вызовов print(...) в Python-коде, игнорируя docstring-примеры
(где >>> print(...) внутри тройных кавычек) и любые строковые литералы.

Используется из scripts/check_logging_canon.sh.
Выводит строки в формате <path>:<line>:<source>; падает с exit 1 при наличии.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _print_calls(tree: ast.Module) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            found.append(node)
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "builtins"
            and func.attr == "print"
        ):
            found.append(node)
    return found


def _docstring_line_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                first = body[0]
                end_lineno = first.end_lineno if hasattr(first, "end_lineno") else first.lineno
                ranges.append((first.lineno, end_lineno))
    return ranges


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    docstring_ranges = _docstring_line_ranges(tree)

    def in_docstring(lineno: int) -> bool:
        for start, end in docstring_ranges:
            if start <= lineno <= end:
                return True
        return False

    bad: list[tuple[int, str]] = []
    lines = source.splitlines()
    for call in _print_calls(tree):
        if in_docstring(call.lineno):
            continue
        line_text = lines[call.lineno - 1] if 0 < call.lineno <= len(lines) else ""
        bad.append((call.lineno, line_text.rstrip()))
    return bad


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: _check_print_calls.py <path> [...]", file=sys.stderr)
        return 2

    excluded = {
        "core/docs",
        "apps/flows/tools",
        "core/eval",
        "apps/browser/engine/playwright_interactor.py",
        "apps/agent/desktop/vendor",
    }

    candidates: list[Path] = []
    for arg in args:
        root = Path(arg)
        if root.is_file():
            candidates.append(root)
        else:
            candidates.extend(p for p in root.rglob("*.py"))

    has_bad = False
    for path in candidates:
        rel = path.as_posix()
        if any(rel.startswith(prefix) or prefix in rel for prefix in excluded):
            continue
        if "/__pycache__/" in rel or "/migrations/versions/" in rel:
            continue
        for lineno, text in _scan_file(path):
            print(f"{rel}:{lineno}:{text}")
            has_bad = True

    return 1 if has_bad else 0


if __name__ == "__main__":
    sys.exit(main())
