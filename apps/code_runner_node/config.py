"""Конфигурация code-runner-node."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class CodeRunnerNodeSettings(BaseSettings):
    """Настройки Node.js sandbox runner."""


_settings_cache = ServiceSettingsCache("code_runner_node", CodeRunnerNodeSettings)
get_code_runner_node_settings = _settings_cache.get
reset_code_runner_node_settings = _settings_cache.reset
