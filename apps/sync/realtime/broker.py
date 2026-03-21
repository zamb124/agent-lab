"""TaskIQ broker для Sync realtime команд.

Один инстанс для enqueue (API/WS) и для `taskiq worker`: очередь "sync".
"""

from taskiq import TaskiqState

from core.logging import get_logger, setup_logging
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

broker = create_broker(queue_name="sync")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="sync")
broker.on_event("startup")(recovery_handler)


async def sync_worker_startup(state: TaskiqState) -> None:
    setup_logging(service_name="sync-worker")
    logger.info("Sync Worker: запуск")


async def sync_worker_shutdown(state: TaskiqState) -> None:
    logger.info("Sync Worker: остановка")


register_worker_events(broker, sync_worker_startup, sync_worker_shutdown)

logger.info("Sync realtime broker создан (queue='sync')")
