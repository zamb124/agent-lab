"""
PythonCompiler - валидация и компиляция Python кода.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from typing import Any

from apps.flows.src.eval.import_policy import (
    filtered_namespace_import_roots,
    validate_import_nodes,
)
from apps.flows.src.eval.inline_tool_sanitize import strip_forbidden_platform_import_lines
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from core.errors import SafeEvalError
from core.inline_python_eval_policy import FORBIDDEN_INLINE_DUNDER_ATTRIBUTES


def _ast_expr_is_constant_truthy(test: ast.expr) -> bool:
    if isinstance(test, ast.Constant):
        return bool(test.value)
    return False


def _forbid_constant_truthy_while_loops(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and _ast_expr_is_constant_truthy(node.test):
            raise SafeEvalError(
                "Запрещён цикл while с постоянным истинным условием (например while True, while 1)"
            )


def _normalize_inline_source(
    code: str,
    strip_platform_imports: bool,
) -> str:
    if not strip_platform_imports:
        return code

    return strip_forbidden_platform_import_lines(code)


def _validate_code(code: str, namespace_keys: frozenset[str]) -> None:
    """Проверяет код на опасные конструкции."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SafeEvalError(f"Syntax error: {e}") from e

    validate_import_nodes(tree, namespace_keys)
    _forbid_constant_truthy_while_loops(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_INLINE_DUNDER_ATTRIBUTES:
                raise SafeEvalError(f"Access to '{node.attr}' is not allowed")


class PythonCompiler:
    """
    Валидация и компиляция Python кода.
    """

    def __init__(
        self,
        namespace_builder: PythonNamespaceBuilder | None = None,
        *,
        strip_platform_imports: bool = True,
    ):
        self.namespace_builder = namespace_builder or PythonNamespaceBuilder()
        self._strip_platform_imports = strip_platform_imports

    def _prepare_source(self, code: str) -> str:
        return _normalize_inline_source(
            code,
            self._strip_platform_imports,
        )

    def validate(self, code: str) -> None:
        """
        Проверяет код на безопасность.

        Args:
            code: Python код

        Raises:
            SafeEvalError: Если код содержит опасные конструкции
        """
        code = self._prepare_source(code)
        namespace = self.namespace_builder.build()
        ns_keys = filtered_namespace_import_roots(namespace)
        _validate_code(code, ns_keys)

    def compile(self, code: str, func_name: str = "run", auto_find: bool = True) -> Callable[..., Any]:
        """
        Компилирует код и возвращает функцию.

        Args:
            code: Python код с определением функции
            func_name: Имя функции для поиска
            auto_find: Автопоиск первой функции если func_name не найден

        Returns:
            Callable - скомпилированная функция

        Raises:
            SafeEvalError: Если код невалиден или функция не найдена
        """
        code = self._prepare_source(code)
        namespace = self.namespace_builder.build()
        ns_keys = filtered_namespace_import_roots(namespace)
        _validate_code(code, ns_keys)

        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}") from e

        if func_name not in namespace:
            # Автопоиск первой функции только для стандартных имен
            if auto_find and func_name in ("run", "execute"):
                match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
                if match:
                    found_func_name = match.group(1)
                    if found_func_name in namespace:
                        return namespace[found_func_name]
            raise SafeEvalError(f"Function '{func_name}' not found in code")

        return namespace[func_name]

    def compile_tool(self, code: str) -> Callable[..., Any]:
        """
        Компилирует inline tool/code-node код и возвращает функцию-точку входа.

        Контракт намеренно function-only:
        1. `run`
        2. `execute`
        3. первая top-level функция в файле

        Args:
            code: Python код

        Returns:
            Callable - скомпилированная функция

        Raises:
            SafeEvalError: Если код невалиден или не найдена top-level функция
        """
        code = self._prepare_source(code)
        namespace = self.namespace_builder.build()
        ns_keys = filtered_namespace_import_roots(namespace)
        _validate_code(code, ns_keys)

        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}") from e

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SafeEvalError(f"Syntax error: {e}") from e

        top_level_funcs = [
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        top_level_func_names = {n.name for n in top_level_funcs}
        for entry_name in ("run", "execute"):
            if entry_name not in top_level_func_names:
                continue
            fn = namespace.get(entry_name)
            if callable(fn):
                return fn

        if top_level_funcs:
            entry_name = top_level_funcs[0].name
            fn = namespace.get(entry_name)
            if callable(fn):
                return fn

        raise SafeEvalError("No top-level function found in code")
