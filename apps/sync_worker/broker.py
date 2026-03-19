"""Sync Worker broker для realtime задач.

Использует очередь "sync" для изоляции от платформенных задач.
"""

from taskiq import TaskiqState

from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)
from core.logging import get_logger, setup_logging

logger = get_logger(__name__)

broker = create_broker(queue_name="sync")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="sync")
broker.on_event("startup")(recovery_handler)


async def sync_worker_startup(state: TaskiqState) -> None:
    """Инициализация Sync Worker при старте."""
    setup_logging(service_name="sync-worker")
    logger.info("Sync Worker: запуск")


async def sync_worker_shutdown(state: TaskiqState) -> None:
    """Остановка Sync Worker."""
    logger.info("Sync Worker: остановка")


register_worker_events(broker, sync_worker_startup, sync_worker_shutdown)

logger.info("Sync Worker broker создан (queue='sync')")
