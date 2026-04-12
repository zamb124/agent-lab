"""Проверка импортов для inline-кода (whitelist)."""

from __future__ import annotations

import ast
from core.errors import SafeEvalError
from core.inline_python_eval_policy import (
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
    import_module_top_level,
)

_MSG_IMPORT_PLATFORM_FORBIDDEN = (
    "В коде ноды нельзя подключать внутренние модули платформы через import. "
    "Нужные возможности уже в окружении: например reader, writer для файлов, llm для модели, "
    "channel и context — см. справку «Глобалы Python» в редакторе."
)


def assert_module_import_allowed(module_name: str) -> None:
    if not module_name:
        raise SafeEvalError("Пустое имя модуля в import")
    root = import_module_top_level(module_name)
    if root in FORBIDDEN_IMPORT_ROOTS:
        raise SafeEvalError(_MSG_IMPORT_PLATFORM_FORBIDDEN)
    if root not in ALLOWED_IMPORT_ROOTS:
        raise SafeEvalError(f"Import of '{module_name}' is not allowed")


def validate_import_nodes(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert_module_import_allowed(alias.name)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                raise SafeEvalError("Relative imports are not allowed in inline code")
            if not node.module:
                raise SafeEvalError("Invalid import: missing module")
            if node.module == "__future__":
                for alias in node.names:
                    if alias.name not in FUTURE_IMPORT_NAMES:
                        raise SafeEvalError(
                            f"from __future__ import {alias.name} is not allowed in inline code"
                        )
            assert_module_import_allowed(node.module)


def safe_inline_import(
    name: str,
    globals: object = None,
    locals: object = None,
    fromlist: tuple = (),
    level: int = 0,
):
    if level != 0:
        raise SafeEvalError("Relative imports are not allowed in inline code")
    assert_module_import_allowed(name)
    import importlib

    return importlib.import_module(name)
