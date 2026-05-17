"""
Точка входа для Sync Worker.

Запуск: taskiq worker apps.sync_worker.worker:worker_app
"""

from apps.sync.config import SyncSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_sync_worker = load_merged_config(service_name="sync_worker", silent=True)
_sync_worker_settings = SyncSettings(**_merged_sync_worker)
setup_worker_logging_early("sync_worker", logging_config=_sync_worker_settings.logging)
set_settings(_sync_worker_settings)

from taskiq import TaskiqState  # noqa: E402

from apps.sync.container import get_sync_container  # noqa: E402
from apps.sync.realtime.broker import broker as worker_app  # noqa: E402
from apps.sync.realtime.broker import recovery_handler  # noqa: E402
from core.billing import set_billing_service  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.push.apns_credentials import resolve_apns_credentials  # noqa: E402
from core.push.apns_service import init_apns_push_service  # noqa: E402
from core.push.fcm_credentials import resolve_fcm_credentials  # noqa: E402
from core.push.fcm_service import init_fcm_push_service  # noqa: E402
from core.push.service import init_web_push_service  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402
from core.websocket.manager import notification_manager  # noqa: E402

logger = get_logger(__name__)


async def sync_worker_startup(state: TaskiqState) -> None:
    settings = _sync_worker_settings
    container = get_sync_container()
    state.container = container
    await recovery_handler()
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
        logger.info("worker.tracing_initialized", service="sync_worker")
    await notification_manager.start_redis_listener(settings.database.redis_url)
    if settings.push.enabled:
        init_web_push_service(
            vapid_private_key=settings.push.vapid_private_key or "",
            vapid_public_key=settings.push.vapid_public_key or "",
            vapid_email=settings.push.vapid_email,
        )
        logger.info("worker.web_push_initialized", service="sync_worker")
    apns = resolve_apns_credentials(settings)
    if apns:
        init_apns_push_service(
            team_id=apns.team_id,
            key_id=apns.key_id,
            private_key_pem=apns.private_key_pem,
            bundle_id=apns.bundle_id,
            use_sandbox=apns.use_sandbox,
        )
        logger.info("worker.apns_initialized", service="sync_worker")
    fcm = resolve_fcm_credentials(settings)
    if fcm:
        init_fcm_push_service(
            project_id=fcm.project_id,
            client_email=fcm.client_email,
            private_key_pem=fcm.private_key_pem,
            token_uri=fcm.token_uri,
        )
        logger.info(
            "worker.fcm_initialized",
            service="sync_worker",
            project_id=fcm.project_id,
        )
    logger.info("worker.starting", service="sync_worker")


async def sync_worker_shutdown(state: TaskiqState) -> None:
    await notification_manager.stop_redis_listener()
    logger.info("worker.stopping", service="sync_worker")


register_worker_events(
    worker_app,
    sync_worker_startup,
    sync_worker_shutdown,
    service_name="sync_worker",
)

import apps.sync.realtime.notification_tasks as _notification_tasks  # noqa: E402
import apps.sync.realtime.tasks as _sync_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (
    _notification_tasks,
    _sync_tasks,
)

__all__ = ["worker_app"]
