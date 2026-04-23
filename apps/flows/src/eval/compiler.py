"""
PythonCompiler - валидация и компиляция Python кода.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Callable, Dict, Optional

from apps.flows.src.eval.import_policy import (
    filtered_namespace_import_roots,
    validate_import_nodes,
)
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from core.errors import SafeEvalError
from core.inline_python_eval_policy import FORBIDDEN_INLINE_DUNDER_ATTRIBUTES


def _normalize_inline_source(
    code: str,
    strip_platform_imports: bool,
) -> str:
    if not strip_platform_imports:
        return code
    from apps.flows.src.eval.inline_tool_sanitize import strip_forbidden_platform_import_lines

    return strip_forbidden_platform_import_lines(code)


def _validate_code(code: str, namespace_keys: frozenset[str]) -> None:
    """Проверяет код на опасные конструкции."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SafeEvalError(f"Syntax error: {e}") from e

    validate_import_nodes(tree, namespace_keys)

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
        namespace_builder: Optional[PythonNamespaceBuilder] = None,
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
    
    def compile(self, code: str, func_name: str = "run", auto_find: bool = True) -> Callable:
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
    
    def compile_tool(self, code: str) -> tuple[Callable | type, bool]:
        """
        Компилирует код tool и возвращает функцию или класс.
        
        Args:
            code: Python код
            
        Returns:
            Tuple[Callable | type, bool] - (функция/класс, is_class)
            
        Raises:
            SafeEvalError: Если код невалиден или не найдена функция/класс
        """
        code = self._prepare_source(code)
        namespace = self.namespace_builder.build()
        ns_keys = filtered_namespace_import_roots(namespace)
        _validate_code(code, ns_keys)

        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}") from e
        
        # Ищем класс наследующий BaseTool
        base_tool_cls = namespace.get("BaseTool")
        if base_tool_cls:
            for name, obj in namespace.items():
                if isinstance(obj, type) and issubclass(obj, base_tool_cls) and obj is not base_tool_cls:
                    return obj, True
        
        # Ищем функцию execute
        if "execute" in namespace:
            return namespace["execute"], False

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SafeEvalError(f"Syntax error: {e}") from e

        top_level_funcs = [
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if top_level_funcs:
            entry_name = top_level_funcs[-1].name
            fn = namespace.get(entry_name)
            if callable(fn):
                return fn, False

        raise SafeEvalError("No function found in code")
