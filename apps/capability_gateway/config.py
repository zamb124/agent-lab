"""Конфигурация capability-gateway."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CapabilityGatewaySettings(BaseSettings):
    """Настройки trusted capability gateway."""


_capability_gateway_settings: CapabilityGatewaySettings | None = None


def get_capability_gateway_settings() -> CapabilityGatewaySettings:
    global _capability_gateway_settings
    if _capability_gateway_settings is None:
        merged_config = load_merged_config(service_name="capability_gateway", silent=True)
        _capability_gateway_settings = CapabilityGatewaySettings.model_validate(merged_config)
    return _capability_gateway_settings


def reset_capability_gateway_settings() -> None:
    global _capability_gateway_settings
    _capability_gateway_settings = None
