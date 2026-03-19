"""TaskIQ broker для Sync realtime команд.

Использует очередь "sync" для изоляции от платформенных и RAG задач.
"""

from core.tasks.broker import create_broker, create_scheduler, create_stale_tasks_recovery
from core.logging import get_logger

logger = get_logger(__name__)

broker = create_broker(queue_name="sync")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="sync")
broker.on_event("startup")(recovery_handler)

logger.info("Sync realtime broker создан (queue='sync')")
