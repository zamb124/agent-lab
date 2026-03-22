"""
Конфигурация для CRM Service.

Расширяет BaseSettings добавляя специфичные для CRM поля.
"""

from typing import Optional
from pydantic import Field

from core.config import BaseSettings


class CRMSettings(BaseSettings):
    """
    Настройки CRM сервиса.
    
    Наследуется от BaseSettings, добавляя специфичные для CRM поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    URL сервиса flows берется из server.flows_service_url (SERVER__FLOWS_SERVICE_URL).
    """
    
    rag_namespace_prefix: str = Field(
        default="crm_",
        description="Префикс namespace для CRM сущностей в RAG"
    )
    max_entities_per_company: int = Field(
        default=10000,
        description="Максимальное количество сущностей на компанию"
    )
    max_notes_per_company: int = Field(
        default=50000,
        description="Максимальное количество заметок на компанию"
    )
    max_tasks_per_company: int = Field(
        default=10000,
        description="Максимальное количество задач на компанию"
    )


_crm_settings: Optional[CRMSettings] = None


def get_crm_settings() -> CRMSettings:
    """
    Получает настройки CRM сервиса.
    
    Создает CRMSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для CRM.
    """
    global _crm_settings
    if _crm_settings is None:
        from core.config.loader import load_merged_config

        merged_config = load_merged_config(service_name="crm")
        _crm_settings = CRMSettings(**merged_config)
    
    return _crm_settings


def reset_crm_settings():
    """Сбрасывает настройки (для тестов)"""
    global _crm_settings
    _crm_settings = None

