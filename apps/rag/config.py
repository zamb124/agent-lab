"""
Конфигурация для RAG Service.
"""


from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class RAGSettings(BaseSettings):
    """
    Настройки RAG сервиса.

    Наследуется от BaseSettings, добавляя специфичные для RAG поля.
    Все базовые поля (database, auth, logging, rag, s3) доступны из родителя.
    """
    pass


_settings_cache = ServiceSettingsCache("rag", RAGSettings)
get_rag_settings = _settings_cache.get
reset_rag_settings = _settings_cache.reset
