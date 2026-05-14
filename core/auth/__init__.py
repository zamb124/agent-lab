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

_lazy_imports = {
    "require_admin": ".decorators",
    "require_auth": ".decorators",
    "validate_body": ".decorators",
    "validate_params": ".decorators",
    "compare_passwords": ".utils",
    "generate_access_token": ".utils",
    "generate_refresh_token": ".utils",
    "generate_session_id": ".utils",
    "get_cache_session_key": ".utils",
    "get_cache_token_key": ".utils",
    "get_token_info": ".utils",
    "hash_password": ".utils",
    "hash_token": ".utils",
}

def __getattr__(name):
    """Ленивый импорт для опциональных зависимостей."""
    if name in _lazy_imports:
        module_name = _lazy_imports[name]
        import importlib
        module = importlib.import_module(module_name, package=__name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ADMIN_GROUP",
    "DEFAULT_PERMISSION",
    "PermissionChecker",
    "permission_checker",
    "PermissionDeniedError",
    "PermissionDeniedA2AError",
    "require_admin",
    "require_auth",
    "validate_body",
    "validate_params",
    "compare_passwords",
    "generate_access_token",
    "generate_refresh_token",
    "generate_session_id",
    "get_cache_session_key",
    "get_cache_token_key",
    "get_token_info",
    "hash_password",
    "hash_token",
]

