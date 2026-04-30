"""
Настройки процесса ``apps/provider_litserve`` из ``services.provider_litserve``.

Параметры порта и воркеров: ``provider_litserve.infra``.
Публичный URL для клиентов RAG: ``provider_litserve.api``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import model_validator
from core.config import BaseSettings
from core.config.loader import load_merged_config


class ProviderLitserveServiceSettings(BaseSettings):
    @model_validator(mode="after")
    def _align_server_with_gateway(self) -> "ProviderLitserveServiceSettings":
        infra = self.provider_litserve.infra
        self.server.name = "litserve"
        self.server.host = infra.host
        self.server.port = infra.gateway_port
        return self


_provider_litserve_settings: Optional[ProviderLitserveServiceSettings] = None


def get_provider_litserve_settings() -> ProviderLitserveServiceSettings:
    global _provider_litserve_settings
    if _provider_litserve_settings is None:
        merged = load_merged_config(service_name="provider_litserve", silent=True)
        _provider_litserve_settings = ProviderLitserveServiceSettings(**merged)
    return _provider_litserve_settings
