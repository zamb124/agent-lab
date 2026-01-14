"""
ChromaWorker broker для RAG задач.

Использует очередь "chroma" для изоляции от платформенных задач.
"""

from taskiq import TaskiqState

from core.tasks.broker import (
    create_broker, 
    create_scheduler, 
    create_stale_tasks_recovery,
    register_worker_events
)
from core.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Создаем broker для RAG задач (queue_name="chroma")
broker = create_broker(queue_name="chroma")
scheduler = create_scheduler(broker)

# Регистрируем recovery зависших задач
recovery_handler = create_stale_tasks_recovery(queue_name="chroma")
broker.on_event("startup")(recovery_handler)


# Обработчики запуска и остановки воркера
async def chroma_worker_startup(state: TaskiqState) -> None:
    """Инициализация ChromaWorker при старте"""
    from apps.chroma_worker.config import get_settings
    from core.rag.factory import get_default_rag_provider
    
    setup_logging(service_name="chroma-worker")
    
    settings = get_settings()
    provider = get_default_rag_provider()
    state.rag_provider = provider
    
    logger.info("ChromaWorker: RAG provider инициализирован")
    logger.info(f"ChromaWorker: используется провайдер {settings.rag.default_provider}")


async def chroma_worker_shutdown(state: TaskiqState) -> None:
    """Остановка ChromaWorker"""
    logger.info("ChromaWorker: остановка")


# Регистрируем worker events
register_worker_events(broker, chroma_worker_startup, chroma_worker_shutdown)

logger.info("✅ ChromaWorker broker создан (queue='chroma')")
