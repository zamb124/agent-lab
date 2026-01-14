"""
Конфигурация для Frontend Service.

Расширяет BaseSettings добавляя специфичные для Frontend поля.
"""

from typing import Optional
from pydantic import Field

from core.config import BaseSettings


class FrontendSettings(BaseSettings):
    """
    Настройки Frontend сервиса.
    
    Наследуется от BaseSettings, добавляя специфичные для Frontend поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """
    
    # Пока специфичных настроек нет, но можно добавить при необходимости
    # Например:
    # session_timeout: int = Field(default=7200, description="Таймаут сессии в секундах")
    pass


_frontend_settings: Optional[FrontendSettings] = None


def get_frontend_settings() -> FrontendSettings:
    """
    Получает настройки Frontend сервиса.
    
    Создает FrontendSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для Frontend.
    """
    global _frontend_settings
    if _frontend_settings is None:
        from pathlib import Path
        from core.config.loader import load_merged_config
        
        service_config_path = Path(__file__).parent / "conf.json"
        merged_config = load_merged_config(service_config_path=service_config_path)
        _frontend_settings = FrontendSettings(**merged_config)
    
    return _frontend_settings


def reset_frontend_settings():
    """Сбрасывает настройки (для тестов)"""
    global _frontend_settings
    _frontend_settings = None

