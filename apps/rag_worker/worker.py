"""RAG Worker (очередь ``rag``).

Запуск: taskiq worker apps.rag_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

import importlib
from apps.rag_worker.config import RAGWorkerSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_settings = RAGWorkerSettings.model_validate(load_merged_config(service_name="rag_worker", silent=True))
setup_worker_logging_early("rag_worker", logging_config=_settings.logging)
set_settings(_settings)

from taskiq import TaskiqState

from apps.platform_tasks.wiring import wire_worker
from apps.rag.container import get_rag_container

from core.billing import set_billing_service
from core.files.processors import initialize_default_processors
from core.logging import get_logger
from core.tasks.worker_bootstrap import build_worker, init_worker_tracing

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.rag.events")

logger = get_logger(__name__)

broker = wire_worker("rag")


async def _startup(state: TaskiqState) -> None:
    container = get_rag_container()
    state.container = container
    initialize_default_processors(container.file_repository)
    set_billing_service(container.billing_service)
    init_worker_tracing("rag_worker", container)
    state.rag_provider = container.rag_provider
    logger.info("worker.rag_provider_initialized", service="rag_worker")


worker_app = build_worker(broker, service_name="rag_worker", queue="rag", on_startup=_startup)

__all__ = ["worker_app"]
