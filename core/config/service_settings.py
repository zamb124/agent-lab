"""Один экземпляр настроек сервиса на процесс.

Каждый сервис объявляет `get_<svc>_settings` / `reset_<svc>_settings` как
методы одного `ServiceSettingsCache`; `reset` нужен только тестам, которые
меняют ENV между запусками.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from core.config.base import BaseSettings, set_settings
from core.config.loader import load_merged_config

SettingsT = TypeVar("SettingsT", bound=BaseSettings)


class ServiceSettingsCache(Generic[SettingsT]):
    """Ленивая загрузка `settings_class` из merged config сервиса."""

    def __init__(
        self,
        service_name: str,
        settings_class: type[SettingsT],
        *,
        register_platform_settings: bool = False,
        finalize: Callable[[SettingsT], SettingsT] | None = None,
    ) -> None:
        self._service_name: str = service_name
        self._settings_class: type[SettingsT] = settings_class
        self._register_platform_settings: bool = register_platform_settings
        self._finalize: Callable[[SettingsT], SettingsT] | None = finalize
        self._instance: SettingsT | None = None

    def get(self) -> SettingsT:
        if self._instance is None:
            merged_config = load_merged_config(service_name=self._service_name, silent=True)
            loaded = self._settings_class.model_validate(merged_config)
            if self._finalize is not None:
                loaded = self._finalize(loaded)
            if self._register_platform_settings:
                set_settings(loaded)
            self._instance = loaded
        return self._instance

    def reset(self) -> None:
        self._instance = None
