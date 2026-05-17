"""
TaskIQ broker для CRM фоновых задач.
"""

from core.logging import get_logger
from core.tasks.broker import create_broker, create_stale_tasks_recovery

logger = get_logger(__name__)

broker = create_broker(queue_name="crm", service_name="crm_worker")

recovery_handler = create_stale_tasks_recovery(queue_name="crm")

logger.info("worker.broker_created", queue="crm")
