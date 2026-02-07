"""
Конфигурация RAG Worker.
"""

from core.config import BaseSettings


class RAGWorkerSettings(BaseSettings):
    """Настройки для RAG Worker"""
    pass


_settings: RAGWorkerSettings | None = None


def get_settings() -> RAGWorkerSettings:
    """Получить singleton settings"""
    global _settings
    if _settings is None:
        _settings = RAGWorkerSettings()
    return _settings
