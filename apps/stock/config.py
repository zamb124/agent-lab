"""
Конфигурация Stock Service.

URL БД берётся из `database.stock_url`, адреса соседей — из `server.*_service_url`.
"""

from pydantic import Field

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class StockSettings(BaseSettings):
    """Настройки сервиса склада."""

    putaway_flow_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        le=60.0,
        description="Дедлайн inline-вызова flow рефлекса putaway; таймаут → move остаётся confirmed",
    )


_settings_cache = ServiceSettingsCache("stock", StockSettings, register_platform_settings=True)
get_stock_settings = _settings_cache.get
reset_stock_settings = _settings_cache.reset
