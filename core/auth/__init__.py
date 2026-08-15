"""
Модуль авторизации.
"""

from core.auth.errors import PermissionDeniedA2AError
from core.errors import PermissionDeniedError

__all__ = [
    "PermissionDeniedError",
    "PermissionDeniedA2AError",
]
