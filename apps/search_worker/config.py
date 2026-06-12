"""Search worker settings."""

from core.config import BaseSettings
from core.config.loader import load_merged_config


class SearchWorkerSettings(BaseSettings):
    pass


_settings: SearchWorkerSettings | None = None


def get_settings() -> SearchWorkerSettings:
    global _settings
    if _settings is None:
        merged = load_merged_config(service_name="search_worker", silent=True)
        _settings = SearchWorkerSettings.model_validate(merged)
    return _settings
