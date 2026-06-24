"""
Конфигурация Worktracker Service.

WorktrackerSettings — тот же BaseSettings, что и у остальных сервисов.
URL БД ядра задач: settings.database.worktracker_url.
"""

from core.config import BaseSettings


class WorktrackerSettings(BaseSettings):
    """Настройки сервиса ядра задач WorkItem."""
