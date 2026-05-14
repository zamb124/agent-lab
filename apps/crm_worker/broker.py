"""
TaskIQ broker для CRM фоновых задач.
"""

from taskiq import TaskiqState

from apps.crm.container import get_crm_container
from core.billing import set_billing_service
from core.config import get_settings
from core.files.processors import initialize_default_processors
from core.logging import get_logger
from core.tasks.broker import (
    create_broker,
    create_stale_tasks_recovery,
    register_worker_events,
)
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name
from core.websocket.manager import notification_manager

logger = get_logger(__name__)

broker = create_broker(queue_name="crm", service_name="crm_worker")

recovery_handler = create_stale_tasks_recovery(queue_name="crm")


async def crm_worker_startup(state: TaskiqState) -> None:
    settings = get_settings()
    container = get_crm_container()
    state.container = container

    reconciled = await container.task_service.reconcile_stale_worker_tasks()
    if reconciled:
        logger.warning(
            "worker.reconcile_stale_crm_tasks",
            service="crm_worker",
            reconciled=reconciled,
        )

    await recovery_handler()

    initialize_default_processors(container.file_repository)
    logger.info("worker.file_processors_initialized", service="crm_worker")
    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service="crm_worker")
    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("crm_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="crm_worker")
    await notification_manager.start_redis_listener(settings.database.redis_url)
    logger.info("worker.starting", service="crm_worker")


async def crm_worker_shutdown(state: TaskiqState) -> None:
    await notification_manager.stop_redis_listener()
    logger.info("worker.stopping", service="crm_worker")


register_worker_events(
    broker,
    crm_worker_startup,
    crm_worker_shutdown,
    service_name="crm_worker",
)

logger.info("worker.broker_created", queue="crm")
