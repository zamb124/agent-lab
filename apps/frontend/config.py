"""
Конфигурация для Frontend Service.

Расширяет BaseSettings добавляя специфичные для фронтенда поля.
"""

from core.config import BaseSettings


class FrontendSettings(BaseSettings):
    """
    Настройки сервиса фронтенда.
    
    Наследуется от BaseSettings, добавляя специфичные для фронтенда поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """
    pass


def get_frontend_settings() -> FrontendSettings:
    """
    Получает настройки сервиса фронтенда.
    
    ВАЖНО: Если settings - BaseSettings (при импорте моделей), просто возвращаем его.
    FrontendSettings будет установлен позже при создании приложения.
    """
    from core.config import get_settings
    settings = get_settings()
    
    return settings




