"""
Core API роутеры.

Общие API эндпоинты которые могут использоваться в разных сервисах.
"""

from core.api.auth import router as auth_router
from core.api.calendar import router as calendar_router
from core.api.integrations import router as integrations_router
from core.api.team import router as team_router

__all__ = ["auth_router", "calendar_router", "integrations_router", "team_router"]

