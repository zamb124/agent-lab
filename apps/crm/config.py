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
    URL agents сервиса берется из server.agents_service_url (SERVER__AGENTS_SERVICE_URL).
    """
    
    chromadb_namespace_prefix: str = Field(
        default="crm_",
        description="Префикс namespace в ChromaDB для CRM сущностей"
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
        from pathlib import Path
        from core.config.loader import load_merged_config
        
        service_config_path = Path(__file__).parent / "conf.json"
        merged_config = load_merged_config(service_config_path=service_config_path)
        _crm_settings = CRMSettings(**merged_config)
    
    return _crm_settings


def reset_crm_settings():
    """Сбрасывает настройки (для тестов)"""
    global _crm_settings
    _crm_settings = None

