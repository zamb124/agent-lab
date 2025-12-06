"""
Frontend Service - FastAPI приложение для фронтенда.

Порт: 8002
БД: shared_db
"""

import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from core.app import create_service_app
from core.files import initialize_default_processors
from core.middleware.profiling import ProfilingMiddleware

from apps.frontend.config import FrontendSettings
from apps.frontend.container import get_frontend_container
from apps.frontend.core.htmx_helpers import HTMXHeaderMiddleware
from apps.frontend.core.plugin_loader import discover_and_load_plugins

logger = logging.getLogger(__name__)


async def on_startup(app: FastAPI, container, settings):
    """Кастомная логика при старте"""
    # Файловые процессоры
    initialize_default_processors(
        file_repository=container.file_repository,
        storage=container.storage
    )
    
    # Плагины
    logger.info("Загрузка плагинов...")
    await discover_and_load_plugins(app)
    
    # Монтирование статики
    _mount_static_files(app)


def _mount_static_files(app: FastAPI):
    """Монтирует статические файлы"""
    frontend_dir = Path(__file__).parent
    project_root = frontend_dir.parent.parent
    
    # Модули
    modules_dir = frontend_dir / "modules"
    for module_path in sorted(modules_dir.iterdir()):
        if module_path.is_dir() and (module_path / "static").exists():
            app.mount(
                f"/static/{module_path.name}",
                StaticFiles(directory=str(module_path / "static")),
                name=f"static-{module_path.name}"
            )
    
    # Страницы
    pages_dir = frontend_dir / "pages"
    for page_path in sorted(pages_dir.iterdir()):
        if page_path.is_dir() and (page_path / "static").exists():
            app.mount(
                f"/static/{page_path.name}",
                StaticFiles(directory=str(page_path / "static")),
                name=f"static-{page_path.name}"
            )
    
    # Shared static
    static_dir = frontend_dir / "shared" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    # Документация
    docs_dir = project_root / "site"
    if docs_dir.exists():
        app.mount("/docs", StaticFiles(directory=str(docs_dir), html=True), name="docs")


# Импорт роутеров
from apps.frontend.api_router import router as frontend_api_router
from apps.frontend.pages_router import router as frontend_pages_router
from apps.frontend.websockets_router import router as frontend_websockets_router
from apps.frontend.websockets.notifications import router as websocket_notifications_router
from apps.frontend.api import models as frontend_models
from apps.frontend.api.mcp import router as mcp_api_router
from apps.frontend.api.debug import router as debug_router
from core.api import auth_router
from apps.agents.api.v1.admin import router as admin_router
from apps.agents.container import get_agents_container


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    return _create_app()


def _create_app() -> FastAPI:
    """Внутренняя функция создания приложения"""
    return create_service_app(
        service_name="frontend",
        settings_class=FrontendSettings,
        get_container=get_frontend_container,
        routers=[
            frontend_api_router,
            frontend_websockets_router,
            mcp_api_router,
            admin_router,
        ],
        pages_routers=[
            frontend_pages_router,
            auth_router,
            websocket_notifications_router,
            debug_router,  # Debug endpoints для E2E тестов
            frontend_models.router,  # /frontend/models/... для HTMX
        ],
        api_version=None,  # Frontend не использует версионирование API
        extra_middlewares=[
            (ProfilingMiddleware, {"log_slow_requests": True, "slow_threshold_ms": 500}),
            (HTMXHeaderMiddleware, {}),
        ],
        extra_state={
            "agents_container": get_agents_container(),
        },
        on_startup=on_startup,
        cors_origins=["*"],  # Debug mode
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        include_crud_routers=False,
        include_broker=True,
        title="Frontend Service",
        description="Фронтенд сервис с HTMX и плагинной системой",
    )


app = create_app()
