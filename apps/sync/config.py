"""
Конфигурация для Sync Service.

SyncSettings — тот же BaseSettings, что и у остальных сервисов. HTTP выставляет
его через create_service_app (слой ``services.sync``), TaskIQ — в
``apps/sync/worker.py`` (слой ``services.sync_worker``).
"""

from pydantic import Field

from core.config import BaseSettings


class SyncSettings(BaseSettings):
    """
    Настройки Sync сервиса.

    URL sync БД: settings.database.sync_url. S3 и прочее — общий блок settings.s3
    (корневой conf.json + conf.local.json, плюс слой services.sync при merge).
    """

    summary_a2a_timeout_seconds: float = Field(
        default=3000.0,
        description="Таймаут A2A вызова summary в flows (секунды).",
    )
