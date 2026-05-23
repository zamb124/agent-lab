"""
Конфигурация RAG Worker.
"""

from core.config import BaseSettings
from core.config.loader import load_merged_config


class RAGWorkerSettings(BaseSettings):
    """Настройки для RAG Worker"""

    pass


_settings: RAGWorkerSettings | None = None


def get_settings() -> RAGWorkerSettings:
    global _settings
    if _settings is None:
        merged = load_merged_config(service_name="rag_worker", silent=True)
        _settings = RAGWorkerSettings.model_validate(merged)
    return _settings
