"""
Настройки процесса ``apps/provider_litserve`` из ``services.provider_litserve``.

Параметры порта и воркеров: ``provider_litserve.infra``.
Канонический URL сервиса для клиентов: ``server.provider_litserve_service_url`` (+ ``/v1``).
"""

from __future__ import annotations

from pydantic import model_validator

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class ProviderLitserveServiceSettings(BaseSettings):
    @model_validator(mode="after")
    def _align_server_with_gateway(self) -> "ProviderLitserveServiceSettings":
        infra = self.provider_litserve.infra
        self.server.name = "litserve"
        self.server.host = infra.host
        self.server.port = infra.gateway_port
        return self


_settings_cache = ServiceSettingsCache("provider_litserve", ProviderLitserveServiceSettings)
get_provider_litserve_settings = _settings_cache.get
