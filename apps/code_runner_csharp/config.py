"""Конфигурация code-runner-csharp."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class CodeRunnerCsharpSettings(BaseSettings):
    """Настройки C# sandbox runner."""


_settings_cache = ServiceSettingsCache("code_runner_csharp", CodeRunnerCsharpSettings)
get_code_runner_csharp_settings = _settings_cache.get
reset_code_runner_csharp_settings = _settings_cache.reset
