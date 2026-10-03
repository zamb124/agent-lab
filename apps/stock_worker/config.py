"""Stock worker settings."""

from core.config import BaseSettings
from core.config.loader import load_merged_config


class StockWorkerSettings(BaseSettings):
    pass


_settings: StockWorkerSettings | None = None


def get_settings() -> StockWorkerSettings:
    global _settings
    if _settings is None:
        merged = load_merged_config(service_name="stock_worker", silent=True)
        _settings = StockWorkerSettings.model_validate(merged)
    return _settings
