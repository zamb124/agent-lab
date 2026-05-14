"""
Главный файл приложения RAG Service.
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.app import create_service_app
from core.logging import get_logger

from .api import (
    documents_router,
    namespaces_router,
    providers_router,
    search_router,
)
from .config import RAGSettings, get_rag_settings
from .container import get_rag_container
from .dependencies import ContainerDep

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container, settings: RAGSettings):
    """Кастомная логика при запуске сервиса RAG"""
    logger.info("RAG Service запускается...")

    if not settings.rag.enabled:
        logger.warning("RAG отключен в конфигурации")
        return

    logger.info(f"RAG провайдер по умолчанию: {settings.rag.default_provider}")

    enabled_providers = [
        name for name, config in settings.rag.providers.items()
        if config.enabled
    ]
    logger.info(f"Включенные провайдеры: {', '.join(enabled_providers)}")


async def on_shutdown(app: FastAPI, container):
    """Кастомная логика при остановке сервиса RAG"""
    logger.info("RAG Service останавливается...")


app = create_service_app(
    service_name="rag",
    settings_class=RAGSettings,
    get_container=get_rag_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        providers_router,
        namespaces_router,
        documents_router,
        search_router,
    ],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    cors_origins=["*"],
    api_version="v1",
    title="RAG Service",
    description="RAG Service - управление документами и семантический поиск",
    version="1.0.0",
)

# Монтирование UI
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount("/rag/ui/static", StaticFiles(directory=ui_path), name="rag_ui")
    logger.info(f"RAG UI смонтирован: {ui_path}")

# Монтирование core/frontend (общая библиотека)
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")


@app.get("/rag")
@app.get("/rag/")
@app.get("/rag/ui")
@app.get("/rag/ui/{path:path}")
async def serve_ui(container: ContainerDep, path: str = ""):
    """Отдает SPA для RAG UI"""
    _ = container
    index_path = ui_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "RAG UI not built yet"}


if __name__ == "__main__":
    settings = get_rag_settings()
    uvicorn.run(
        "apps.rag.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )


