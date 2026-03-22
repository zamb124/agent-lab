"""
Конфигурация для Sync Service.

SyncSettings — тот же BaseSettings, что и у остальных сервисов. Процесс sync (HTTP
или TaskIQ worker) должен один раз выставить глобальные настройки через
set_settings(SyncSettings(**load_merged_config(service_name="sync"))): так делает
create_service_app в main и загрузчик apps.sync_worker.worker.
"""

from core.config import BaseSettings


class SyncSettings(BaseSettings):
    """
    Настройки Sync сервиса.

    URL sync БД: settings.database.sync_url. S3 и прочее — общий блок settings.s3
    (корневой conf.json + conf.local.json, плюс слой services.sync при merge).
    """

    pass
