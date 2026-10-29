"""Имя метода показывает порядок, если тело сортирует строки."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report

_CLOSED = (
    "_asc",
    "_desc",
    "unordered",
    "breadth",
    "by_score_desc",
    "by_priority_asc",
    "by_distance",
    "in_serialization_order",
    "by_sort_then_row_id",
    "by_tag_asc",
)
_ORDER_MARKS = ("order_by", "ORDER BY", ".sort(")
_SKIP_PARTS = frozenset({"__pycache__", "ui", "node_modules", "vendor"})


def _ordered_names(path: Path) -> list[str]:
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{path}: {exc}"]
    lines = source.splitlines()
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name.startswith("op_") or node.name.startswith("_"):
            continue
        if any(token in node.name for token in _CLOSED):
            continue
        end = node.end_lineno or node.lineno
        segment = "\n".join(lines[node.lineno - 1 : end])
        if any(mark in segment for mark in _ORDER_MARKS):
            found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {node.name}")
    return found


def main() -> int:
    errors: list[str] = []
    for root_name in ("apps", "core"):
        root = REPO_ROOT / root_name
        for path in root.rglob("*.py"):
            if _SKIP_PARTS.intersection(path.parts):
                continue
            errors.extend(_ordered_names(path))
    return report("model_method_order_names", errors)


if __name__ == "__main__":
    raise SystemExit(main())
