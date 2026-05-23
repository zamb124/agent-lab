"""Конфигурация scheduler сервиса."""


from core.config import BaseSettings
from core.config.loader import load_merged_config


class SchedulerSettings(BaseSettings):
    """Настройки scheduler сервиса."""


_scheduler_settings: SchedulerSettings | None = None


def get_scheduler_settings() -> SchedulerSettings:
    global _scheduler_settings
    if _scheduler_settings is None:
        merged_config = load_merged_config(service_name="scheduler", silent=True)
        _scheduler_settings = SchedulerSettings.model_validate(merged_config)
    return _scheduler_settings


def reset_scheduler_settings() -> None:
    global _scheduler_settings
    _scheduler_settings = None
