"""
Конфигурация для Frontend Service.

Расширяет BaseSettings добавляя специфичные для фронтенда поля.
"""

import os

from core.config import BaseSettings


class FrontendSettings(BaseSettings):
    """
    Настройки сервиса фронтенда.
    
    Наследуется от BaseSettings, добавляя специфичные для фронтенда поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """
    
    def get_crm_service_url(self) -> str:
        """Возвращает URL CRM сервиса, с учетом переменной окружения для тестов"""
        test_url = os.environ.get("TEST_CRM_SERVICE_URL")
        if test_url:
            return test_url
        return getattr(self.server, "crm_service_url", "http://localhost:8003")


def get_frontend_settings() -> FrontendSettings:
    """
    Получает настройки сервиса фронтенда.
    
    ВАЖНО: Если settings - BaseSettings (при импорте моделей), просто возвращаем его.
    FrontendSettings будет установлен позже при создании приложения.
    """
    from core.config import get_settings
    settings = get_settings()
    
    return settings




