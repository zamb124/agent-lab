"""Конфигурация guest_runtime."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class GuestRuntimeSettings(BaseSettings):
    """Настройки фермы code_agent."""


_settings_cache = ServiceSettingsCache("guest_runtime", GuestRuntimeSettings)
get_guest_runtime_settings = _settings_cache.get
reset_guest_runtime_settings = _settings_cache.reset
