"""Конфигурация code-runner-csharp."""

from __future__ import annotations

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CodeRunnerCsharpSettings(BaseSettings):
    """Настройки C# sandbox runner."""


_code_runner_csharp_settings: CodeRunnerCsharpSettings | None = None


def get_code_runner_csharp_settings() -> CodeRunnerCsharpSettings:
    global _code_runner_csharp_settings
    if _code_runner_csharp_settings is None:
        merged_config = load_merged_config(service_name="code_runner_csharp", silent=True)
        _code_runner_csharp_settings = CodeRunnerCsharpSettings.model_validate(merged_config)
    return _code_runner_csharp_settings


def reset_code_runner_csharp_settings() -> None:
    global _code_runner_csharp_settings
    _code_runner_csharp_settings = None
