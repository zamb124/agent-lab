"""
Константы безопасности для выполнения inline кода.

Политика whitelist: см. core.inline_python_eval_policy.
"""

from core.inline_python_eval_policy import (
    ALLOWED_BUILTINS,
    ALLOWED_IMPORT_ROOTS,
    FORBIDDEN_IMPORT_ROOTS,
    FUTURE_IMPORT_NAMES,
)

__all__ = [
    "ALLOWED_BUILTINS",
    "ALLOWED_IMPORT_ROOTS",
    "FORBIDDEN_IMPORT_ROOTS",
    "FUTURE_IMPORT_NAMES",
]
