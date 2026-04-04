"""
TaskIQ broker для CRM фоновых задач.
"""

import redis.asyncio as redis
from taskiq import TaskiqState

from apps.crm.container import get_crm_container
from core.billing import set_billing_service
from core.config import get_settings
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name
from core.logging import get_logger, setup_logging
from core.scheduler import get_schedule_source
from core.websocket.manager import notification_manager
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)

logger = get_logger(__name__)

broker = create_broker(queue_name="crm")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="crm")
broker.on_event("startup")(recovery_handler)


async def _ensure_reconcile_schedule() -> None:
    settings = get_settings()
    redis_client = redis.from_url(settings.database.redis_url, decode_responses=True)
    schedule_key = "crm:daily_summary:v1:reconcile:schedule_id"
    saved_schedule_id = await redis_client.get(schedule_key)
    if saved_schedule_id is not None:
        await redis_client.aclose()
        return

    source = get_schedule_source(settings.database.redis_url)
    await source.startup()
    from apps.crm_worker.tasks.daily_summary_tasks import reconcile_daily_summary_task

    schedule = await reconcile_daily_summary_task.kicker().schedule_by_cron(
        source,
        "0 * * * *",
    )
    await redis_client.set(schedule_key, schedule.schedule_id)
    await redis_client.aclose()
    logger.info(f"CRM Worker: reconcile schedule создан, id={schedule.schedule_id}")


async def crm_worker_startup(state: TaskiqState) -> None:
    setup_logging(service_name="crm_worker")
    settings = get_settings()
    container = get_crm_container()
    set_billing_service(container.billing_service)
    logger.info("CRM Worker: BillingService инициализирован")
    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("crm_worker")
            set_span_repository(container.span_repository)
        logger.info("CRM Worker: трейсинг инициализирован")
    await notification_manager.start_redis_listener(settings.database.redis_url)
    await _ensure_reconcile_schedule()
    logger.info("CRM Worker: запуск")


async def crm_worker_shutdown(state: TaskiqState) -> None:
    await notification_manager.stop_redis_listener()
    logger.info("CRM Worker: остановка")


register_worker_events(broker, crm_worker_startup, crm_worker_shutdown)

logger.info("CRM Worker broker создан (queue='crm')")
