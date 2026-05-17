"""Конфигурация code-runner-go."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CodeRunnerGoSettings(BaseSettings):
    """Настройки Go sandbox runner."""


_code_runner_go_settings: CodeRunnerGoSettings | None = None


def get_code_runner_go_settings() -> CodeRunnerGoSettings:
    global _code_runner_go_settings
    if _code_runner_go_settings is None:
        merged_config = load_merged_config(service_name="code_runner_go", silent=True)
        _code_runner_go_settings = CodeRunnerGoSettings.model_validate(merged_config)
    return _code_runner_go_settings


def reset_code_runner_go_settings() -> None:
    global _code_runner_go_settings
    _code_runner_go_settings = None
