"""
Core API роутеры.

Общие API эндпоинты которые могут использоваться в разных сервисах.
"""

from core.api.auth import router as auth_router
from core.api.calendar import router as calendar_router

__all__ = ["auth_router", "calendar_router"]

