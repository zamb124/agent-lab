"""Конфигурация code-runner-go."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class CodeRunnerGoSettings(BaseSettings):
    """Настройки Go sandbox runner."""


_settings_cache = ServiceSettingsCache("code_runner_go", CodeRunnerGoSettings)
get_code_runner_go_settings = _settings_cache.get
reset_code_runner_go_settings = _settings_cache.reset
