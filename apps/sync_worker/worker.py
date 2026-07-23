"""Sync Worker (очередь ``sync``).

Запуск: taskiq worker apps.sync_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.sync.config import SyncSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_sync_worker_settings = SyncSettings.model_validate(
    load_merged_config(service_name="sync_worker", silent=True)
)
setup_worker_logging_early("sync_worker", logging_config=_sync_worker_settings.logging)
set_settings(_sync_worker_settings)

from taskiq import TaskiqState

from apps.platform_tasks.wiring import wire_worker
from apps.sync.container import get_sync_container
from core.billing import set_billing_service
from core.files.processors import initialize_default_processors
from core.logging import get_logger
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.fcm_credentials import resolve_fcm_credentials
from core.push.fcm_service import init_fcm_push_service
from core.push.service import init_web_push_service
from core.tasks.worker_bootstrap import build_worker, init_worker_tracing

logger = get_logger(__name__)

broker = wire_worker("sync")


async def _startup(state: TaskiqState) -> None:
    settings = _sync_worker_settings
    container = get_sync_container()
    state.container = container
    initialize_default_processors(container.file_repository)
    set_billing_service(container.billing_service)
    init_worker_tracing("sync_worker", container)
    if settings.push.enabled:
        _ = init_web_push_service(
            vapid_private_key=settings.push.vapid_private_key or "",
            vapid_public_key=settings.push.vapid_public_key or "",
            vapid_email=settings.push.vapid_email,
        )
        logger.info("worker.web_push_initialized", service="sync_worker")
    apns = resolve_apns_credentials(settings)
    if apns:
        _ = init_apns_push_service(
            team_id=apns.team_id,
            key_id=apns.key_id,
            private_key_pem=apns.private_key_pem,
            bundle_id=apns.bundle_id,
            use_sandbox=apns.use_sandbox,
        )
        logger.info("worker.apns_initialized", service="sync_worker")
    fcm = resolve_fcm_credentials(settings.push)
    if fcm:
        _ = init_fcm_push_service(
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


async def _shutdown(state: TaskiqState) -> None:
    _ = state


worker_app = build_worker(
    broker,
    service_name="sync_worker",
    queue="sync",
    on_startup=_startup,
    on_shutdown=_shutdown,
)

__all__ = ["worker_app"]
