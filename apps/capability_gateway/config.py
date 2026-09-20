"""Конфигурация capability-gateway."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class CapabilityGatewaySettings(BaseSettings):
    """Настройки trusted capability gateway."""


_settings_cache = ServiceSettingsCache("capability_gateway", CapabilityGatewaySettings)
get_capability_gateway_settings = _settings_cache.get
reset_capability_gateway_settings = _settings_cache.reset
