"""Конфигурация scheduler сервиса."""


from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class SchedulerSettings(BaseSettings):
    """Настройки scheduler сервиса."""


_settings_cache = ServiceSettingsCache("scheduler", SchedulerSettings)
get_scheduler_settings = _settings_cache.get
reset_scheduler_settings = _settings_cache.reset
