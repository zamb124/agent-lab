"""
Конфигурация для Agents Service.

Расширяет BaseSettings добавляя специфичные для агентов поля.
"""

from pydantic import Field

from core.config import BaseSettings


class AgentsSettings(BaseSettings):
    """
    Настройки сервиса агентов.
    
    Наследуется от BaseSettings, добавляя специфичные для агентов поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """
    
    max_agents: int = Field(
        default=100,
        description="Максимальное количество агентов в компании"
    )
    max_flows: int = Field(
        default=100,
        description="Максимальное количество flows в компании"
    )
    max_tools: int = Field(
        default=500,
        description="Максимальное количество инструментов"
    )
    enable_migration_on_startup: bool = Field(
        default=True,
        description="Запускать ли миграцию агентов при старте"
    )
    enable_auto_cleanup: bool = Field(
        default=True,
        description="Автоматическая очистка старых сессий"
    )
    session_cleanup_interval: int = Field(
        default=600,
        description="Интервал очистки сессий (секунды)"
    )
    session_timeout: int = Field(
        default=1800,
        description="Таймаут неактивных сессий (секунды)"
    )


def get_agents_settings() -> AgentsSettings:
    """
    Получает настройки сервиса агентов.
    
    ВАЖНО: Если settings - BaseSettings (при импорте моделей), просто возвращаем его.
    AgentsSettings будет установлен позже при создании приложения.
    """
    from core.config import get_settings
    settings = get_settings()
    
    return settings

