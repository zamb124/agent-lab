"""Конфигурация code-runner-python."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class CodeRunnerPythonSettings(BaseSettings):
    """Настройки Python sandbox runner."""


_settings_cache = ServiceSettingsCache("code_runner_python", CodeRunnerPythonSettings)
get_code_runner_python_settings = _settings_cache.get
reset_code_runner_python_settings = _settings_cache.reset
