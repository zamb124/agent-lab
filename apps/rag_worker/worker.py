"""
RAG Worker startup/shutdown события и регистрация tasks.

Глобальный ``core.config.get_settings()`` должен совпадать с HTTP-сервисом **rag**
(слой ``services.rag``), иначе S3 и фабрика провайдера не увидят bucket **files** и др.
"""

from core.config import set_settings
from core.config.loader import load_merged_config

from apps.rag_worker.config import RAGWorkerSettings

set_settings(RAGWorkerSettings(**load_merged_config(service_name="rag")))

from apps.rag_worker.broker import broker
from core.logging import get_logger

logger = get_logger(__name__)

import apps.rag_worker.tasks.indexing_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.search_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.maintenance_tasks  # noqa: F401, E402
