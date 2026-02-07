"""
RAG Worker startup/shutdown события и регистрация tasks.
"""

from apps.rag_worker.broker import broker
from core.logging import get_logger

logger = get_logger(__name__)

# Импорт всех задач для регистрации в broker
import apps.rag_worker.tasks.indexing_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.search_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.maintenance_tasks  # noqa: F401, E402
