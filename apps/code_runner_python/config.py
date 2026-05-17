"""Конфигурация code-runner-python."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CodeRunnerPythonSettings(BaseSettings):
    """Настройки Python sandbox runner."""


_code_runner_python_settings: CodeRunnerPythonSettings | None = None


def get_code_runner_python_settings() -> CodeRunnerPythonSettings:
    global _code_runner_python_settings
    if _code_runner_python_settings is None:
        merged_config = load_merged_config(service_name="code_runner_python", silent=True)
        _code_runner_python_settings = CodeRunnerPythonSettings.model_validate(merged_config)
    return _code_runner_python_settings


def reset_code_runner_python_settings() -> None:
    global _code_runner_python_settings
    _code_runner_python_settings = None
