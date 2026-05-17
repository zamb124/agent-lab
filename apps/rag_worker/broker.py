"""TaskIQ broker для RAG worker."""

from core.logging import get_logger
from core.tasks.broker import create_broker, create_scheduler, create_stale_tasks_recovery

logger = get_logger(__name__)

broker = create_broker(queue_name="rag", service_name="rag_worker")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="rag")

logger.info("worker.broker_created", queue="rag")
