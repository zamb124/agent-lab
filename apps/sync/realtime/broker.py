"""TaskIQ broker для Sync realtime команд.

Один инстанс для enqueue (API/WS) и для `taskiq worker`: очередь "sync".
"""

from core.logging import get_logger
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
)

logger = get_logger(__name__)

broker = create_broker(queue_name="sync", service_name="sync_worker")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="sync")

logger.info("worker.broker_created", queue="sync")
