"""Секция `agent` платформенных настроек в тестах, меняющих ENV между кейсами."""

from __future__ import annotations

from core.config import BaseSettings, get_settings


def reset_agent_settings() -> None:
    """Перечитывает `settings.agent` из conf + ENV в живой singleton процесса."""
    reloaded = BaseSettings()
    get_settings().agent = reloaded.agent
