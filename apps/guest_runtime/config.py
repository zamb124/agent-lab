"""Конфигурация guest_runtime."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class GuestRuntimeSettings(BaseSettings):
    """Настройки фермы code_agent."""


_guest_runtime_settings: GuestRuntimeSettings | None = None


def get_guest_runtime_settings() -> GuestRuntimeSettings:
    global _guest_runtime_settings
    if _guest_runtime_settings is None:
        merged_config = load_merged_config(service_name="guest_runtime", silent=True)
        _guest_runtime_settings = GuestRuntimeSettings.model_validate(merged_config)
    return _guest_runtime_settings


def reset_guest_runtime_settings() -> None:
    global _guest_runtime_settings
    _guest_runtime_settings = None
