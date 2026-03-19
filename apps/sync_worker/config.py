"""Конфигурация Sync Worker."""

from core.config import BaseSettings


class SyncWorkerSettings(BaseSettings):
    """Настройки для Sync Worker"""
    pass


_settings: SyncWorkerSettings | None = None


def get_settings() -> SyncWorkerSettings:
    """Получить singleton settings"""
    global _settings
    if _settings is None:
        _settings = SyncWorkerSettings()
    return _settings
