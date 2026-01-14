"""
Конфигурация ChromaWorker.
"""

from core.config import BaseSettings


class ChromaWorkerSettings(BaseSettings):
    """Настройки для ChromaWorker"""
    pass


_settings: ChromaWorkerSettings | None = None


def get_settings() -> ChromaWorkerSettings:
    """Получить singleton settings"""
    global _settings
    if _settings is None:
        _settings = ChromaWorkerSettings()
    return _settings


