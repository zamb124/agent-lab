"""
Конфигурация для RAG Service.
"""


from core.config import BaseSettings
from core.config.loader import load_merged_config


class RAGSettings(BaseSettings):
    """
    Настройки RAG сервиса.

    Наследуется от BaseSettings, добавляя специфичные для RAG поля.
    Все базовые поля (database, auth, logging, rag, s3) доступны из родителя.
    """
    pass


_rag_settings: RAGSettings | None = None


def get_rag_settings() -> RAGSettings:
    """
    Получает настройки RAG сервиса.

    Создает RAGSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для RAG.
    """
    global _rag_settings
    if _rag_settings is None:
        merged_config = load_merged_config(service_name="rag", silent=True)
        _rag_settings = RAGSettings.model_validate(merged_config)

    return _rag_settings


def reset_rag_settings():
    """Сбрасывает настройки (для тестов)"""
    global _rag_settings
    _rag_settings = None

