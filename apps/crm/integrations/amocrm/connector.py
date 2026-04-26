"""
Коннектор AmoCRM: делегирует HTTP и импорт сервису, обновляет integrations в namespace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService
from apps.crm.integrations.amocrm.type_extensions import (
    AMO_OPTIONAL_FIELDS_BY_TYPE_ID,
    amo_canonical_type_ids,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.models.identity_models import NamespaceCRMSettings

if TYPE_CHECKING:
    from apps.crm.container import CRMContainer


class AmoCRMConnector:
    provider_id = "amocrm"
    integration_provider = IntegrationProvider.AMOCRM

    def worker_short_label(self) -> str:
        return "AmoCRM"

    def entities_sync_runs_in_worker(self) -> bool:
        return True

    def custom_fields_sync_runs_in_worker(self) -> bool:
        return True

    def __init__(self, container: CRMContainer) -> None:
        self._container = container
        self._service = AmoCRMIntegrationService(
            oauth_service=container.oauth_service,
            entity_repository=container.entity_repository,
            entity_type_repository=container.entity_type_repository,
            relationship_repository=container.relationship_repository,
            entity_service=container.entity_service,
        )

    async def build_authorize_url(
        self,
        *,
        namespace_name: str,
        subdomain: str,
        return_path: str,
        company_id: str,
        user_id: str,
        return_origin: str | None = None,
    ) -> str:
        service = f"amocrm:{namespace_name.strip()}"
        return await self._container.oauth_service.build_auth_url(
            provider=IntegrationProvider.AMOCRM,
            service=service,
            scopes=[],
            user_id=user_id,
            company_id=company_id,
            return_path=return_path,
            amocrm_subdomain=subdomain.strip(),
            return_origin=return_origin,
        )

    async def sync_entities(self, namespace_name: str, **kwargs: Any) -> dict[str, int]:
        return await self._service.sync_entities(namespace_name, **kwargs)

    async def sync_custom_field_catalog(self, namespace_name: str, **kwargs: Any) -> dict[str, int]:
        return await self._service.sync_custom_field_catalog(namespace_name, **kwargs)

    async def ensure_namespace_ready(
        self,
        *,
        namespace_name: str,
        company_id: str,
    ) -> None:
        repo = self._container.entity_type_repository
        ns = namespace_name.strip()
        if not ns:
            raise ValueError("namespace_name обязателен")
        for type_id in sorted(amo_canonical_type_ids()):
            existing_type = await repo.get_by_type_id(type_id, company_id=company_id)
            if existing_type is None:
                raise ValueError(
                    f"Для интеграции AmoCRM в пространстве «{ns}» нужен тип сущности «{type_id}» "
                    "в компании. Создайте пространство из шаблона sales или amocrm либо добавьте тип вручную."
                )
            await repo.add_namespace_ids(type_id, [ns], company_id=company_id)
            extra = AMO_OPTIONAL_FIELDS_BY_TYPE_ID.get(type_id)
            if extra:
                await repo.merge_optional_fields_if_absent(
                    type_id,
                    company_id=company_id,
                    extra=extra,
                )

    async def on_credential_saved(self, credential: IntegrationCredential) -> None:
        if credential.provider != IntegrationProvider.AMOCRM:
            return
        if not credential.service.startswith("amocrm:"):
            return
        namespace_name = credential.service.split(":", 1)[1]
        if not namespace_name:
            return
        sub = credential.metadata.get("amocrm_subdomain")
        if not isinstance(sub, str) or not sub.strip():
            return
        sub = sub.strip()
        existing = await self._container.namespace_repository.get(namespace_name)
        if existing is None or existing.company_id != credential.company_id:
            return
        await self.ensure_namespace_ready(
            namespace_name=namespace_name,
            company_id=credential.company_id,
        )
        prev = existing.crm_settings
        integ_prev = dict(prev.integrations) if prev is not None else {}
        amo_prev = dict(integ_prev.get("amocrm") or {}) if isinstance(integ_prev.get("amocrm"), dict) else {}
        if amo_prev.get("subdomain") == sub:
            return
        base = prev if prev is not None else NamespaceCRMSettings()
        integ = dict(base.integrations)
        amo = dict(integ.get("amocrm") or {}) if isinstance(integ.get("amocrm"), dict) else {}
        amo["subdomain"] = sub
        integ["amocrm"] = amo
        existing.crm_settings = base.model_copy(update={"integrations": integ})
        await self._container.namespace_repository.set(existing)

    async def manifest_item(
        self,
        *,
        namespace_name: str,
        company_id: str,
        user_id: str,
        crm_settings: NamespaceCRMSettings | None,
    ) -> dict[str, Any]:
        display: str | None = None
        if crm_settings is not None:
            block = crm_settings.integrations.get("amocrm")
            if isinstance(block, dict):
                raw = block.get("subdomain")
                if isinstance(raw, str) and raw.strip():
                    display = raw.strip()
        cred = await self._container.oauth_service.get_valid_token(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.AMOCRM,
            service=f"amocrm:{namespace_name}",
        )
        connected = cred is not None
        return {
            "provider_id": self.provider_id,
            "connected": connected,
            "display": display,
        }
