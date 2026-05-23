"""
Конфигурация для Frontend Service.

Расширяет BaseSettings добавляя специфичные для Frontend поля.
"""


from core.config import BaseSettings
from core.config.loader import load_merged_config


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


_frontend_settings: FrontendSettings | None = None


def get_frontend_settings() -> FrontendSettings:
    """
    Получает настройки Frontend сервиса.

    Создает FrontendSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для Frontend.
    """
    global _frontend_settings
    if _frontend_settings is None:
        merged_config = load_merged_config(service_name="frontend", silent=True)
        _frontend_settings = FrontendSettings.model_validate(merged_config)

    return _frontend_settings


def reset_frontend_settings():
    """Сбрасывает настройки (для тестов)"""
    global _frontend_settings
    _frontend_settings = None
