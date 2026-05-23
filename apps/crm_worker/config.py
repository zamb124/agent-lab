"""
Конфигурация CRM Worker.
"""

from core.config import BaseSettings
from core.config.loader import load_merged_config


class CRMWorkerSettings(BaseSettings):
    """Настройки для CRM Worker."""

    pass


_settings: CRMWorkerSettings | None = None


def get_settings() -> CRMWorkerSettings:
    global _settings
    if _settings is None:
        merged = load_merged_config(service_name="crm_worker", silent=True)
        _settings = CRMWorkerSettings.model_validate(merged)
    return _settings
