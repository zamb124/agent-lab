"""TaskIQ broker для Sync realtime команд.

Один инстанс для enqueue (API/WS) и для `taskiq worker`: очередь "sync".
"""

from taskiq import TaskiqState

from apps.sync.container import get_sync_container
from core.billing import set_billing_service
from core.config import get_settings
from core.logging import get_logger, setup_logging
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.service import init_web_push_service
from core.tasks.broker import (
    create_broker,
    create_scheduler,
    create_stale_tasks_recovery,
    register_worker_events,
)
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name
from core.websocket.manager import notification_manager

logger = get_logger(__name__)

broker = create_broker(queue_name="sync")
scheduler = create_scheduler(broker)

recovery_handler = create_stale_tasks_recovery(queue_name="sync")
broker.on_event("startup")(recovery_handler)


async def sync_worker_startup(state: TaskiqState) -> None:
    setup_logging(service_name="sync_worker")
    settings = get_settings()
    container = get_sync_container()
    state.container = container
    set_billing_service(container.billing_service)
    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("sync_worker")
            set_span_repository(container.span_repository)
        logger.info("Sync Worker: трейсинг инициализирован")
    await notification_manager.start_redis_listener(settings.database.redis_url)
    if settings.push.enabled:
        init_web_push_service(
            vapid_private_key=settings.push.vapid_private_key or "",
            vapid_public_key=settings.push.vapid_public_key or "",
            vapid_email=settings.push.vapid_email,
        )
        logger.info("Sync Worker: WebPushService инициализирован")
    apns = resolve_apns_credentials(settings)
    if apns:
        init_apns_push_service(
            team_id=apns.team_id,
            key_id=apns.key_id,
            private_key_pem=apns.private_key_pem,
            bundle_id=apns.bundle_id,
            use_sandbox=apns.use_sandbox,
        )
        logger.info("Sync Worker: ApnsPushService инициализирован")
    logger.info("Sync Worker: запуск")


async def sync_worker_shutdown(state: TaskiqState) -> None:
    await notification_manager.stop_redis_listener()
    logger.info("Sync Worker: остановка")


register_worker_events(broker, sync_worker_startup, sync_worker_shutdown)

logger.info("Sync realtime broker создан (queue='sync')")
