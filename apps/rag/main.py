"""
Главный файл приложения RAG Service.
"""

import importlib
from pathlib import Path

from fastapi import FastAPI

from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.files.reader.service import FileReader
from core.logging import get_logger

from .api import (
    documents_router,
    namespaces_router,
    providers_router,
    search_router,
)
from .config import RAGSettings, get_rag_settings
from .container import RAGContainer, get_rag_container
from .realtime.command_router import register_rag_ws_commands

logger = get_logger(__name__)
_ = importlib.import_module("apps.rag.events")


async def on_startup(app: FastAPI, container: RAGContainer, settings: RAGSettings) -> None:
    """Кастомная логика при запуске сервиса RAG"""
    _ = app
    logger.info("RAG Service запускается...")

    register_rag_ws_commands()
    if not settings.rag.enabled:
        logger.warning("RAG отключен в конфигурации")
        return
    _ = container.rag_provider
    FileReader.configure_asset_persist(container.files_service)
    logger.info(f"RAG провайдер по умолчанию: {settings.rag.default_provider}")

    enabled_providers = [
        name for name, config in settings.rag.providers.items()
        if config.enabled
    ]
    logger.info(f"Включенные провайдеры: {', '.join(enabled_providers)}")


async def on_shutdown(app: FastAPI, container: RAGContainer) -> None:
    """Кастомная логика при остановке сервиса RAG"""
    _ = app, container
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

mount_service_spa(app, public_segment="rag", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("rag", "apps.rag.main:app", get_rag_settings())

