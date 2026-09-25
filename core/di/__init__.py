"""Service Kit — единый DI платформы.

``apps/<svc>/di.py``: класс ``<Svc>Di(ServiceDi)`` с полями-компонентами, recipes для того,
что не собирается из ``__init__``, и alias ``Di`` для boundary. Платформенные компоненты —
``core.di.platform.PlatformDi``.
"""

from core.di.boundary import http_di, require_di, require_task_di, task_di
from core.di.errors import DiError
from core.di.kit import (
    DiPlan,
    DiT,
    ProcessIdentity,
    Recipe,
    ServiceDi,
    build_di,
    check_di,
    process_roots,
    recipe,
)
from core.di.process import open_di
from core.di.reflection import DiKey
from core.di.state import clear_task_di, reset_app_di, set_app_di, set_task_di

__all__ = [
    "DiError",
    "DiKey",
    "DiPlan",
    "DiT",
    "ProcessIdentity",
    "Recipe",
    "ServiceDi",
    "build_di",
    "check_di",
    "clear_task_di",
    "http_di",
    "open_di",
    "process_roots",
    "recipe",
    "reset_app_di",
    "require_di",
    "require_task_di",
    "set_app_di",
    "set_task_di",
    "task_di",
]
