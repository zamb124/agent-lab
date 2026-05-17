"""Конфигурация code-runner-node."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CodeRunnerNodeSettings(BaseSettings):
    """Настройки Node.js sandbox runner."""


_code_runner_node_settings: CodeRunnerNodeSettings | None = None


def get_code_runner_node_settings() -> CodeRunnerNodeSettings:
    global _code_runner_node_settings
    if _code_runner_node_settings is None:
        merged_config = load_merged_config(service_name="code_runner_node", silent=True)
        _code_runner_node_settings = CodeRunnerNodeSettings.model_validate(merged_config)
    return _code_runner_node_settings


def reset_code_runner_node_settings() -> None:
    global _code_runner_node_settings
    _code_runner_node_settings = None
