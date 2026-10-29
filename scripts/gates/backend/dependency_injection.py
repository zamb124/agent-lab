#!/usr/bin/env python3
"""Service Kit DI gate.

Каждый ``apps/<process>/di.py`` — один ``<Process>Di``,
alias ``Di = Annotated[<Process>Di, http_di(<Process>Di), task_di(<Process>Di)]``,
граф проходит ``check_di``, каждое собственное поле читается boundary-кодом как
``di.<field>``, DI импортируется только из boundary, параметр DI называется ``di``,
recipe и lifecycle зависят от конкретных компонентов, а не от DI процесса.
"""

from __future__ import annotations

import ast
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import final, override

from scripts.gates.kit import REPO_ROOT

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.di import DiError, ServiceDi, check_di  # noqa: E402

ROOTS: tuple[str, ...] = ("apps", "core", "tests", "scripts")
SKIP_PARTS: frozenset[str] = frozenset(
    {"vendor", "__pycache__", "desktop", "node_modules", "assets"}
)
SELF_PATH = "scripts/gates/backend/dependency_injection.py"
PLATFORM_DI_MODULE = "core/di/platform.py"

DI_PACKAGE_NAMES: frozenset[str] = frozenset(
    {"dependency_injector", "dishka", "injector", "lagom", "punq", "wireup", "that_depends", "svcs"}
)
BOUNDARY_FILE_NAMES: frozenset[str] = frozenset(
    {"main.py", "di.py", "worker.py", "backfill.py", "conftest.py", "scheduler.py"}
)
BOUNDARY_DIR_PARTS: frozenset[str] = frozenset({"api", "realtime", "tasks"})
CORE_BOUNDARY_PREFIXES: tuple[str, ...] = (
    "core/api/",
    "core/app/",
    "core/di/",
    "core/middleware/",
    "core/realtime/",
    "core/websocket/",
    "core/files/api.py",
    "core/tasks/worker_bootstrap.py",
)

@dataclass(frozen=True)
class Violation:
    path: str
    detail: str


@dataclass(frozen=True)
class DiModule:
    """``di.py`` процесса: класс ``<Process>Di`` и область boundary-кода процесса."""

    path: str
    module: str
    class_name: str
    own_fields: tuple[str, ...]
    scope: tuple[str, ...]


def _python_files() -> list[Path]:
    paths: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            paths.append(path)
    return paths


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _name(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return None


def _is_boundary_path(path: str) -> bool:
    path_obj = Path(path)
    if path.startswith(("tests/", "scripts/")):
        return True
    if path.startswith("core/"):
        if path.startswith(CORE_BOUNDARY_PREFIXES):
            return True
        return path_obj.name == "operations.py" or path_obj.name.endswith("_operations.py")
    if path_obj.name in BOUNDARY_FILE_NAMES or path_obj.name.startswith("worker_"):
        return True
    if path_obj.name.endswith(("_tasks.py", "_worker.py", "operations.py")):
        return True
    return bool(BOUNDARY_DIR_PARTS & set(path_obj.parts))


def _pascal(process_dir: str) -> str:
    return "".join(part.capitalize() for part in process_dir.split("_"))


def _is_di_module(module: str) -> bool:
    return module == "core.di.platform" or (module.startswith("apps.") and module.endswith(".di"))


@final
class DiBoundaryVisitor(ast.NodeVisitor):
    """DI читается только на boundary и только параметром ``di``."""

    path: str
    owner_stack: list[str]
    violations: list[Violation]
    di_class_names: frozenset[str]

    def __init__(self, path: str, di_class_names: frozenset[str]) -> None:
        self.path = path
        self.owner_stack = []
        self.violations = []
        self.di_class_names = di_class_names

    @property
    def owner(self) -> str:
        if not self.owner_stack:
            return "<module>"
        return ".".join(self.owner_stack)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.owner_stack.append(node.name)
        self.generic_visit(node)
        _ = self.owner_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.owner_stack.append(node.name)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            annotation_name = _name(argument.annotation)
            is_di_annotation = annotation_name == "Di" or annotation_name in self.di_class_names
            if is_di_annotation and argument.arg != "di" and not self.path.startswith("core/di/"):
                self.violations.append(
                    Violation(self.path, f"{self.owner}({argument.arg}): DI parameter is named 'di'")
                )
            if is_di_annotation and not _is_boundary_path(self.path):
                self.violations.append(
                    Violation(self.path, f"{self.owner}: DI reaches domain code below the boundary")
                )
        self.generic_visit(node)
        _ = self.owner_stack.pop()

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module if node.module is not None else ""
        if module.split(".", 1)[0] in DI_PACKAGE_NAMES:
            self.violations.append(Violation(self.path, f"external DI framework import: {module}"))
        if _is_di_module(module) and not _is_boundary_path(self.path):
            self.violations.append(
                Violation(self.path, f"{module}: DI is imported only by process boundary code")
            )
        self.generic_visit(node)

    @override
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".", 1)[0] in DI_PACKAGE_NAMES:
                self.violations.append(
                    Violation(self.path, f"external DI framework import: {alias.name}")
                )
        self.generic_visit(node)

def _recipe_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    wrapped: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _name(node.func) == "recipe" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Name):
                wrapped.add(first.id)
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name in wrapped or any(_name(decorator) == "recipe" for decorator in node.decorator_list):
            functions.append(node)
    return functions


def _recipe_violations(path: str, tree: ast.Module, di_class_names: frozenset[str]) -> list[Violation]:
    """Recipe и lifecycle — шаги графа: DI процесса появляется только после них."""
    violations: list[Violation] = []
    for function in _recipe_functions(tree):
        arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        for argument in arguments:
            annotation_name = _name(argument.annotation)
            if annotation_name == "Di" or annotation_name in di_class_names:
                violations.append(
                    Violation(
                        path,
                        f"@recipe {function.name}({argument.arg}): "
                        + "recipe depends on the exact components, not on the process DI",
                    )
                )
    return violations


def _di_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for statement in tree.body:
        if isinstance(statement, ast.ClassDef) and statement.name == class_name:
            return statement
    return None


def _own_fields(node: ast.ClassDef) -> tuple[str, ...]:
    fields: list[str] = []
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            fields.append(statement.target.id)
    return tuple(fields)


def _field_violations(path: str, node: ast.ClassDef) -> list[Violation]:
    violations: list[Violation] = []
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and statement.value is not None:
            violations.append(
                Violation(path, f"{node.name}.{_name(statement.target)}: DI fields have no defaults")
            )
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.append(Violation(path, f"{node.name}.{statement.name}: DI class has no methods"))
    return violations


def _alias_matches(tree: ast.Module, class_name: str) -> bool:
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id != "Di":
            continue
        value = statement.value
        if not isinstance(value, ast.Subscript) or _name(value.value) != "Annotated":
            return False
        if not isinstance(value.slice, ast.Tuple) or len(value.slice.elts) != 3:
            return False
        first, http_marker, task_marker = value.slice.elts
        return (
            _name(first) == class_name
            and _marker_matches(http_marker, "http_di", class_name)
            and _marker_matches(task_marker, "task_di", class_name)
        )
    return False


def _marker_matches(node: ast.expr, function: str, class_name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and _name(node.func) == function
        and len(node.args) == 1
        and _name(node.args[0]) == class_name
    )


def _di_modules() -> tuple[list[DiModule], list[Violation]]:
    modules: list[DiModule] = []
    violations: list[Violation] = []
    candidates = [REPO_ROOT / PLATFORM_DI_MODULE, *sorted((REPO_ROOT / "apps").glob("*/di.py"))]
    for path in candidates:
        relative_path = _relative(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        if relative_path == PLATFORM_DI_MODULE:
            class_name = "PlatformDi"
            scope = ("apps/", "core/")
            module = "core.di.platform"
        else:
            process_dir = path.parent.name
            class_name = f"{_pascal(process_dir)}Di"
            scope = (f"apps/{process_dir}/",)
            module = f"apps.{process_dir}.di"
        node = _di_class(tree, class_name)
        if node is None:
            violations.append(Violation(relative_path, f"module declares class {class_name}"))
            continue
        violations.extend(_field_violations(relative_path, node))
        if not _alias_matches(tree, class_name):
            violations.append(
                Violation(
                    relative_path,
                    f"Di = Annotated[{class_name}, http_di({class_name}), task_di({class_name})]",
                )
            )
        modules.append(
            DiModule(
                path=relative_path,
                module=module,
                class_name=class_name,
                own_fields=_own_fields(node),
                scope=scope,
            )
        )
    return modules, violations


def _graph_violations(modules: list[DiModule]) -> list[Violation]:
    violations: list[Violation] = []
    for di_module in modules:
        loaded = importlib.import_module(di_module.module)
        di_class = loaded.__dict__.get(di_module.class_name)
        if not isinstance(di_class, type) or not issubclass(di_class, ServiceDi):
            violations.append(Violation(di_module.path, f"{di_module.class_name} is not a ServiceDi"))
            continue
        try:
            _ = check_di(di_class)
        except DiError as error:
            violations.extend(Violation(di_module.path, problem) for problem in error.problems)
    return violations


def _di_field_reads(trees: dict[str, ast.Module]) -> dict[str, set[str]]:
    reads: dict[str, set[str]] = {}
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "di":
                    reads.setdefault(node.attr, set()).add(path)
    return reads


def _unused_field_violations(
    modules: list[DiModule],
    reads: dict[str, set[str]],
) -> list[Violation]:
    violations: list[Violation] = []
    for di_module in modules:
        for field in di_module.own_fields:
            readers = reads.get(field, set())
            if not any(
                reader.startswith(di_module.scope) and reader != di_module.path and not reader.startswith("tests/")
                for reader in readers
            ):
                violations.append(
                    Violation(
                        di_module.path,
                        f"{di_module.class_name}.{field}: no boundary code reads di.{field}",
                    )
                )
    return violations


def collect() -> list[Violation]:
    modules, violations = _di_modules()
    di_class_names = frozenset({"ServiceDi", *(module.class_name for module in modules)})
    trees: dict[str, ast.Module] = {}
    for path in _python_files():
        relative_path = _relative(path)
        if relative_path == SELF_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        trees[relative_path] = tree
        visitor = DiBoundaryVisitor(relative_path, di_class_names)
        visitor.visit(tree)
        violations.extend(visitor.violations)
        if not relative_path.startswith("tests/"):
            violations.extend(_recipe_violations(relative_path, tree, di_class_names))
    violations.extend(_graph_violations(modules))
    violations.extend(_unused_field_violations(modules, _di_field_reads(trees)))
    return sorted(violations, key=lambda violation: (violation.path, violation.detail))


def main() -> int:
    violations = collect()
    if violations:
        print("check_dependency_injection_canon: FAIL — Service Kit violations:")
        for violation in violations:
            print(f"  {violation.path}: {violation.detail}")
        return 1
    print("check_dependency_injection_canon: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
