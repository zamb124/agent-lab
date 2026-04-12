"""
PythonCompiler - валидация и компиляция Python кода.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Callable, Dict, Optional

from apps.flows.src.eval.import_policy import validate_import_nodes
from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from core.errors import SafeEvalError


def _validate_code(code: str) -> None:
    """Проверяет код на опасные конструкции."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SafeEvalError(f"Syntax error: {e}")

    validate_import_nodes(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SafeEvalError(f"Access to '{node.attr}' is not allowed")


class PythonCompiler:
    """
    Валидация и компиляция Python кода.
    """
    
    def __init__(self, namespace_builder: Optional[PythonNamespaceBuilder] = None):
        self.namespace_builder = namespace_builder or PythonNamespaceBuilder()
    
    def validate(self, code: str) -> None:
        """
        Проверяет код на безопасность.
        
        Args:
            code: Python код
            
        Raises:
            SafeEvalError: Если код содержит опасные конструкции
        """
        _validate_code(code)
    
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
        self.validate(code)
        
        namespace = self.namespace_builder.build()
        
        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}")
        
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
        self.validate(code)
        
        namespace = self.namespace_builder.build()
        
        try:
            exec(code, namespace)
        except Exception as e:
            raise SafeEvalError(f"Compilation error: {e}")
        
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
