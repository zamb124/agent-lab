"""TaskIQ broker for search worker."""

from core.logging import get_logger
from core.tasks.broker import create_broker, create_scheduler, create_stale_tasks_recovery

logger = get_logger(__name__)

broker = create_broker(queue_name="search", service_name="search_worker")
scheduler = create_scheduler(broker)
recovery_handler = create_stale_tasks_recovery(queue_name="search")

logger.info("worker.broker_created", queue="search")
