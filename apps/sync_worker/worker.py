"""Sync Worker (очередь ``sync``).

Запуск: taskiq worker apps.sync_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.sync.config import SyncSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_sync_worker_settings = SyncSettings.model_validate(
    load_merged_config(service_name="sync_worker", silent=True)
)
setup_worker_logging_early("sync_worker", logging_config=_sync_worker_settings.logging)
set_settings(_sync_worker_settings)
set_files_route_segment(resolve_files_route_segment("sync_worker"))

from apps.sync.di import SyncDi
from apps.worker_manifest import wire_worker
from core.di import recipe
from core.logging import get_logger
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.fcm_credentials import resolve_fcm_credentials
from core.push.fcm_service import init_fcm_push_service
from core.push.service import init_web_push_service
from core.tasks.worker_bootstrap import build_worker

logger = get_logger(__name__)


async def init_sync_worker_push(settings: SyncSettings) -> None:
    """Web Push, APNs и FCM, если в настройках воркера заданы ключи."""
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
        logger.info("worker.fcm_initialized", service="sync_worker", project_id=fcm.project_id)


broker = wire_worker("sync")
worker_app = build_worker(
    broker,
    service_name="sync_worker",
    queue="sync",
    settings=_sync_worker_settings,
    di_class=SyncDi,
    database="sync_url",
    lifecycle=(recipe(init_sync_worker_push),),
)

__all__ = ["worker_app"]
