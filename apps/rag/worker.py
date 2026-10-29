"""RAG Worker (очередь ``rag``).

Запуск: taskiq worker apps.rag.worker:worker_app
"""

# ruff: noqa: E402, I001

import importlib

from apps.rag.config import RAGSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = RAGSettings.model_validate(
    load_merged_config(service_name="rag_worker", silent=True)
)
setup_worker_logging_early("rag_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("rag_worker"))

from apps.rag.di import RagDi
from apps.worker_manifest import wire_worker
from core.di import recipe
from core.files.reader.service import FileReader
from core.files.service import FilesService
from core.logging import get_logger
from core.tasks.worker_bootstrap import build_worker

_ = importlib.import_module("apps.rag.events")

logger = get_logger(__name__)


async def configure_rag_file_reader(files_service: FilesService) -> None:
    """Persist ассетов FileReader тем же FilesService, что и HTTP-процесс."""
    FileReader.configure_asset_persist(files_service)
    logger.info("worker.rag_provider_initialized", service="rag_worker")


broker = wire_worker("rag")
worker_app = build_worker(
    broker,
    service_name="rag_worker",
    queue="rag",
    settings=_settings,
    di_class=RagDi,
    database="rag_url",
    lifecycle=(recipe(configure_rag_file_reader),),
)

__all__ = ["worker_app"]
