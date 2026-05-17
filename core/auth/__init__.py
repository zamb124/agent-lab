"""
Модуль авторизации и permissions.
"""

from core.auth.errors import PermissionDeniedA2AError
from core.auth.permissions import (
    ADMIN_GROUP,
    DEFAULT_PERMISSION,
    PermissionChecker,
    permission_checker,
)
from core.errors import PermissionDeniedError

__all__ = [
    "ADMIN_GROUP",
    "DEFAULT_PERMISSION",
    "PermissionChecker",
    "permission_checker",
    "PermissionDeniedError",
    "PermissionDeniedA2AError",
]
