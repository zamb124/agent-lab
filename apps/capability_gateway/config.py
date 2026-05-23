"""Конфигурация capability-gateway."""

from __future__ import annotations

from pydantic import Field

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CapabilityGatewaySettings(BaseSettings):
    """Настройки trusted capability gateway."""

    capability_manifest_cache_enabled: bool = Field(
        default=True,
        description="Кэшировать собранный capability manifest, чтобы не дергать flows на каждый execution.",
    )
    capability_manifest_cache_ttl_seconds: int = Field(
        default=60,
        ge=1,
        description="TTL Redis/in-memory кэша capability manifest.",
    )
    capability_manifest_cache_key: str = Field(
        default="capability_gateway:manifest:v1",
        description="Redis key для shared cache capability manifest.",
    )


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
