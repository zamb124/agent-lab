"""
RAG Worker startup/shutdown события и регистрация tasks.
"""

from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

from apps.rag_worker.config import RAGWorkerSettings

_merged_rag_worker = load_merged_config(service_name="rag_worker", silent=True)
_rag_worker_settings = RAGWorkerSettings(**_merged_rag_worker)
setup_worker_logging_early("rag_worker", logging_config=_rag_worker_settings.logging)
set_settings(_rag_worker_settings)

from apps.rag_worker.broker import broker as worker_app

# Импорт всех задач для регистрации в worker app
import apps.rag_worker.tasks.indexing_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.search_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.maintenance_tasks  # noqa: F401, E402

__all__ = ["worker_app"]
