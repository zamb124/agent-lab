"""
CRM Routes - разбиты по доменам
"""

from .pages import router as pages_router
from .dashboard import router as dashboard_router
from .notes import router as notes_router
from .entities import router as entities_router
from .tasks import router as tasks_router
from .graph import router as graph_router
from .templates import router as templates_router
from .access_requests import router as access_requests_router
from .profile import router as profile_router

__all__ = [
    "pages_router",
    "dashboard_router",
    "notes_router",
    "entities_router",
    "tasks_router",
    "graph_router",
    "templates_router",
    "access_requests_router",
    "profile_router",
]

