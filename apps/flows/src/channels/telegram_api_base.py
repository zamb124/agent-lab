"""Базовый URL Telegram Bot API (без зависимости от ChannelHandler — без циклов)."""

from __future__ import annotations

from core.config import get_settings
from core.types import JsonObject


def get_telegram_api_base(config: JsonObject | None = None) -> str:
    """
    Возвращает базовый URL для Telegram API.

    Приоритет:
    1. config["api_base"] — для тестов / local stub
    2. settings.telegram.api_base — production
    """
    raw_api_base = config.get("api_base") if config is not None else None
    if isinstance(raw_api_base, str) and raw_api_base:
        return raw_api_base
    return get_settings().telegram.api_base


__all__ = ["get_telegram_api_base"]
