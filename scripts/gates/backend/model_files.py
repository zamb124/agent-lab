"""Один PlatformModel на файл в core/ и apps/; рядом с пакетом models/ нет models.py."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report

_SKIP_PARTS = frozenset({"__pycache__", "node_modules", "vendor"})
_LEGACY_MODULES = (
    "core/ai/models.py",
    "core/datasources/models.py",
    "core/db/models/rag.py",
    "core/mail/models.py",
    "core/models/identity_models.py",
    "core/worktracker/models.py",
    "apps/flows/src/models/a2a_projection.py",
)


def _base_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _is_table_class(node: ast.ClassDef) -> bool:
    if any(_base_name(base) == "PlatformModel" for base in node.bases):
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            target = child.target.id
            value = child.value
        elif isinstance(child, ast.Assign):
            names = [target.id for target in child.targets if isinstance(target, ast.Name)]
            if "is_table" not in names:
                continue
            target = "is_table"
            value = child.value
        else:
            continue
        if target == "is_table" and isinstance(value, ast.Constant) and value.value is True:
            return True
    return False


def _table_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(1 for node in tree.body if isinstance(node, ast.ClassDef) and _is_table_class(node))


def collect_errors() -> list[str]:
    errors: list[str] = []
    for relative in _LEGACY_MODULES:
        if (REPO_ROOT / relative).is_file():
            errors.append(f"{relative}: tables belong in the package")
    for base in (REPO_ROOT / "core", REPO_ROOT / "apps"):
        for package in base.rglob("models"):
            if not package.is_dir() or _SKIP_PARTS.intersection(package.parts):
                continue
            sibling = package.parent / "models.py"
            if sibling.is_file():
                errors.append(f"{sibling.relative_to(REPO_ROOT).as_posix()}: tables belong in the package")
        for path in base.rglob("*.py"):
            if _SKIP_PARTS.intersection(path.parts):
                continue
            try:
                count = _table_count(path)
            except SyntaxError as exc:
                errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {exc}")
                continue
            if count > 1:
                rel = path.relative_to(REPO_ROOT).as_posix()
                errors.append(f"{rel}: expected at most one PlatformModel, found {count}")
    return errors


def main() -> int:
    return report("model_files", collect_errors())


if __name__ == "__main__":
    raise SystemExit(main())
