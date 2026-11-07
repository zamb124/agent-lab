"""
Главный файл приложения RAG Service.
"""

import importlib
from collections.abc import AsyncIterator
from pathlib import Path

from apps.rag.config import RAGSettings, get_rag_settings
from apps.rag.di import RagDi
from apps.rag.realtime.command_router import RAG_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.billing.service import BillingService
from core.di import recipe
from core.files.reader.service import FileReader
from core.files.service import FilesService
from core.logging import get_logger
from core.rag.factory import get_rag_provider
from core.text_transforms import TextTransformService

from .api import (
    documents_router,
    namespaces_router,
    providers_router,
    search_router,
)

logger = get_logger(__name__)
_ = importlib.import_module("apps.rag.events")


async def rag_http_lifecycle(
    settings: RAGSettings,
    files_service: FilesService,
    billing_service: BillingService,
) -> AsyncIterator[None]:
    """Провайдер и persist ассетов FileReader, пока rag включён."""
    logger.info("rag.service")
    if settings.rag.enabled:
        _ = get_rag_provider(settings=settings, billing_service=billing_service)
        FileReader.configure_asset_persist(files_service)
        FileReader.configure_text_transform(TextTransformService(billing_service))
        logger.info("rag.startup.default_provider", provider=settings.rag.default_provider)
        enabled_providers = [
            name for name, config in settings.rag.providers.items() if config.enabled
        ]
        logger.info("rag.startup.enabled_providers", providers=enabled_providers)
    else:
        logger.warning("rag.rag")
    yield
    logger.info("rag.service")


app = create_service_app(
    "rag",
    RAGSettings,
    RagDi,
    database="rag_url",
    operations=RAG_OPERATIONS,
    lifecycle=(recipe(rag_http_lifecycle),),
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        providers_router,
        namespaces_router,
        documents_router,
        search_router,
    ],
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
