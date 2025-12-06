"""
Router для CRM UI - standalone интерфейс Networkle

Этот файл агрегирует все роуты CRM из подмодулей:
- pages: главные страницы
- dashboard: дашборд partials
- notes: заметки
- entities: сущности
- tasks: задачи
- graph: граф знаний и поиск
- templates: шаблоны заметок
- access_requests: запросы доступа
- profile: профиль пользователя
"""

from fastapi import APIRouter

from .routes.pages import router as pages_router
from .routes.dashboard import router as dashboard_router
from .routes.notes import router as notes_router
from .routes.entities import router as entities_router
from .routes.tasks import router as tasks_router
from .routes.graph import router as graph_router
from .routes.templates import router as templates_router
from .routes.access_requests import router as access_requests_router
from .routes.profile import router as profile_router
from .routes.sharing import router as sharing_router

router = APIRouter(prefix="/crm", tags=["crm"])

# Подключаем все роуты
router.include_router(pages_router)
router.include_router(dashboard_router)
router.include_router(notes_router)
router.include_router(entities_router)
router.include_router(tasks_router)
router.include_router(graph_router)
router.include_router(templates_router)
router.include_router(access_requests_router)
router.include_router(profile_router)
router.include_router(sharing_router)
