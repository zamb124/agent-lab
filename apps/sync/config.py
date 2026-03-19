"""
Конфигурация для Sync Service.

Расширяет BaseSettings. URL sync БД берётся из settings.database.sync_url.
"""

from typing import Optional
from pathlib import Path

from core.config import BaseSettings
from core.config.loader import load_merged_config


class SyncSettings(BaseSettings):
    """
    Настройки Sync сервиса.

    Наследуется от BaseSettings, все базовые поля (database, auth, logging, etc)
    доступны из родителя. URL sync БД: settings.database.sync_url.
    """
    pass


_sync_settings: Optional[SyncSettings] = None


def get_sync_settings() -> SyncSettings:
    """
    Получает настройки Sync сервиса.

    Создает SyncSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для Sync.
    """
    global _sync_settings
    if _sync_settings is None:
        service_config_path = Path(__file__).parent / "conf.json"
        merged_config = load_merged_config(service_config_path=service_config_path)
        _sync_settings = SyncSettings(**merged_config)

    return _sync_settings


def reset_sync_settings():
    """Сбрасывает настройки (для тестов)"""
    global _sync_settings
    _sync_settings = None
