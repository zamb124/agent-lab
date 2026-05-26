"""
Контракт коннектора внешней интеграции уровня namespace (CRM).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from core.integrations.guided_integration_error import OAuthErrorLocale
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.models.identity_models import NamespaceCRMSettings
from core.types import JsonObject

IntegrationProgressFn = Callable[[str, int], Awaitable[None]]


@runtime_checkable
class NamespaceIntegrationConnector(Protocol):
    """Один провайдер интеграции для пространства (namespace)."""

    provider_id: str
    integration_provider: IntegrationProvider

    def worker_short_label(self) -> str:
        """Подпись провайдера в уведомлениях и логах воркера (не technical id)."""
        ...

    def entities_sync_runs_in_worker(self) -> bool:
        """True — POST .../sync ставит TaskIQ-задачу; False — синхронный ответ HTTP."""
        ...

    def custom_fields_sync_runs_in_worker(self) -> bool:
        """True — POST .../custom_fields/sync ставит задачу; False — синхронный HTTP."""
        ...

    async def build_authorize_url(
        self,
        *,
        namespace_name: str,
        subdomain: str,
        return_path: str,
        company_id: str,
        user_id: str,
        return_origin: str | None = None,
        oauth_ui_locale: OAuthErrorLocale | None = None,
    ) -> str:
        """URL OAuth для подключения (открыть в браузере)."""
        ...

    async def sync_entities(
        self,
        namespace_name: str,
        *,
        on_progress: IntegrationProgressFn | None = None,
    ) -> dict[str, int]: ...

    async def sync_custom_field_catalog(
        self,
        namespace_name: str,
        *,
        on_progress: IntegrationProgressFn | None = None,
    ) -> dict[str, int]: ...

    async def on_credential_saved(self, credential: IntegrationCredential) -> None:
        """После сохранения OAuth credential: метаданные namespace (без секретов)."""
        ...

    async def ensure_namespace_ready(
        self,
        *,
        namespace_name: str,
        company_id: str,
    ) -> None:
        """
        Готовит пространство: копирует отсутствующие строки EntityType для полей интеграции
        из пространства default (или создаёт их иным способом коннектора) и дополняет
        optional_fields без затирания уже объявленных ключей.
        """
        ...

    async def manifest_item(
        self,
        *,
        namespace_name: str,
        company_id: str,
        user_id: str,
        crm_settings: NamespaceCRMSettings | None,
    ) -> JsonObject:
        """Строка для GET .../integrations (список карточек в UI)."""
        ...
