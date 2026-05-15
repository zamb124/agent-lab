"""
Реестр коннекторов интеграций namespace: диспетчеризация по provider и после OAuth.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from apps.crm.integrations.protocol import NamespaceIntegrationConnector
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.models.identity_models import NamespaceCRMSettings

_CRM_UI_ROOT = Path(__file__).resolve().parents[1] / "ui"


def _integration_svg_path(provider_id: str) -> Path:
    return _CRM_UI_ROOT / "assets" / "integrations" / f"{provider_id}.svg"


class IntegrationRegistry:
    def __init__(self, connectors: Iterable[NamespaceIntegrationConnector]) -> None:
        self._by_id: dict[str, NamespaceIntegrationConnector] = {}
        self._by_provider: dict[IntegrationProvider, NamespaceIntegrationConnector] = {}
        for connector in connectors:
            self._register(connector)

    def _register(self, connector: NamespaceIntegrationConnector) -> None:
        icon = _integration_svg_path(connector.provider_id)
        if not icon.is_file():
            raise ValueError(
                f"Для интеграции «{connector.provider_id}» нужен SVG в CRM UI: {icon}"
            )
        self._by_id[connector.provider_id] = connector
        self._by_provider[connector.integration_provider] = connector

    def get(self, provider_id: str) -> NamespaceIntegrationConnector:
        connector = self._by_id.get(provider_id)
        if connector is None:
            raise KeyError(f"Неизвестный провайдер интеграции: {provider_id}")
        return connector

    def known_provider_ids(self) -> list[str]:
        return sorted(self._by_id.keys())

    async def dispatch_credential_saved(self, credential: IntegrationCredential) -> None:
        connector = self._by_provider.get(credential.provider)
        if connector is None:
            return
        await connector.on_credential_saved(credential)

    async def build_manifest(
        self,
        *,
        namespace_name: str,
        company_id: str,
        user_id: str,
        crm_settings: NamespaceCRMSettings | None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for connector in self._by_id.values():
            row = await connector.manifest_item(
                namespace_name=namespace_name,
                company_id=company_id,
                user_id=user_id,
                crm_settings=crm_settings,
            )
            items.append(row)
        return items
