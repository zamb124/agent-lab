"""
Коннектор AmoCRM: делегирует HTTP и импорт сервису, обновляет integrations в namespace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import cast as type_cast
from urllib.parse import quote

from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService, AmoProgressFn
from apps.crm.integrations.amocrm.type_extensions import (
    AMO_OPTIONAL_FIELDS_BY_TYPE_ID,
    amo_canonical_type_ids,
)
from apps.crm.types import JsonObject
from core.integrations.guided_integration_error import (
    GuidedIntegrationError,
    GuidedIntegrationLink,
    OAuthErrorLocale,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.models.identity_models import NamespaceCRMSettings

if TYPE_CHECKING:
    from apps.crm.db.repositories.entity_repository import EntityRepository
    from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
    from apps.crm.db.repositories.relationship_repository import RelationshipRepository
    from apps.crm.services.entity_service import EntityService
    from apps.crm.services.namespace_template_service import NamespaceTemplateService
    from apps.crm.services.task_service import TaskService
    from core.db.repositories.namespace_repository import NamespaceRepository
    from core.identity.integration_external_author import IntegrationExternalAuthorService
    from core.integrations.oauth_service import OAuthService


class AmoCRMConnector:
    provider_id: str = "amocrm"
    integration_provider: IntegrationProvider = IntegrationProvider.AMOCRM

    def worker_short_label(self) -> str:
        return "AmoCRM"

    def entities_sync_runs_in_worker(self) -> bool:
        return True

    def custom_fields_sync_runs_in_worker(self) -> bool:
        return True

    def __init__(
        self,
        *,
        oauth_service: OAuthService,
        entity_repository: EntityRepository,
        entity_type_repository: EntityTypeRepository,
        relationship_repository: RelationshipRepository,
        entity_service: EntityService,
        namespace_repository: NamespaceRepository,
        task_service: TaskService,
        integration_external_author: IntegrationExternalAuthorService,
        namespace_template_service: NamespaceTemplateService,
    ) -> None:
        self._oauth_service: OAuthService = oauth_service
        self._entity_type_repository: EntityTypeRepository = entity_type_repository
        self._namespace_repository: NamespaceRepository = namespace_repository
        self._namespace_template_service: NamespaceTemplateService = namespace_template_service
        self._service: AmoCRMIntegrationService = AmoCRMIntegrationService(
            oauth_service=oauth_service,
            entity_repository=entity_repository,
            entity_type_repository=entity_type_repository,
            relationship_repository=relationship_repository,
            entity_service=entity_service,
            namespace_repository=namespace_repository,
            task_service=task_service,
            integration_external_author=integration_external_author,
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
        oauth_ui_locale: OAuthErrorLocale | None = None,
    ) -> str:
        service = f"amocrm:{namespace_name.strip()}"
        return await self._oauth_service.build_auth_url(
            provider=IntegrationProvider.AMOCRM,
            service=service,
            scopes=[],
            user_id=user_id,
            company_id=company_id,
            return_path=return_path,
            amocrm_subdomain=subdomain.strip(),
            return_origin=return_origin,
            oauth_ui_locale=oauth_ui_locale,
        )

    @staticmethod
    def _as_json_object(value: object) -> JsonObject | None:
        if not isinstance(value, dict):
            return None
        result: JsonObject = {}
        for key, item in type_cast(dict[object, object], value).items():
            if not isinstance(key, str):
                return None
            result[key] = item
        return result

    async def sync_entities(
        self,
        namespace_name: str,
        *,
        on_progress: AmoProgressFn | None = None,
    ) -> dict[str, int]:
        return await self._service.sync_entities(namespace_name, on_progress=on_progress)

    async def sync_custom_field_catalog(
        self,
        namespace_name: str,
        *,
        on_progress: AmoProgressFn | None = None,
    ) -> dict[str, int]:
        return await self._service.sync_custom_field_catalog(
            namespace_name,
            on_progress=on_progress,
        )

    async def ensure_namespace_ready(
        self,
        *,
        namespace_name: str,
        company_id: str,
    ) -> None:
        repo = self._entity_type_repository
        ns = namespace_name.strip()
        if not ns:
            raise ValueError("namespace_name обязателен")
        for type_id in sorted(amo_canonical_type_ids()):
            existing_type = await repo.get_by_type_id(
                type_id,
                namespace=ns,
                company_id=company_id,
            )
            if existing_type is None:
                src_default = await repo.get_by_type_id(
                    type_id,
                    namespace="default",
                    company_id=company_id,
                )
                if src_default is None:
                    raise GuidedIntegrationError(
                        code="crm_amocrm_missing_canonical_entity_type",
                        title_ru="Не хватает типа сущности для AmoCRM",
                        title_en="Missing entity type for AmoCRM",
                        message_ru=(
                            f"Для интеграции AmoCRM в пространстве «{ns}» нужен тип сущности "
                            f"«{type_id}» в компании. Создайте пространство из шаблона sales "
                            "либо добавьте тип вручную."
                        ),
                        message_en=(
                            f"AmoCRM integration in space «{ns}» requires entity type "
                            f"«{type_id}» for this company. Create a space from the sales template "
                            "or add the type manually."
                        ),
                        steps_ru=(
                            "В разделе «Пространства» создайте пространство из шаблона sales.",
                            f"Или откройте карточку «{ns}» и добавьте тип «{type_id}» вручную.",
                            "Затем снова подключите AmoCRM в настройках интеграций.",
                        ),
                        steps_en=(
                            "In Spaces, create a space from the sales template.",
                            f"Or open space «{ns}» and add type «{type_id}» manually.",
                            "Then connect AmoCRM again in integration settings.",
                        ),
                        links=(
                            GuidedIntegrationLink(
                                href="/crm/settings/spaces",
                                label_ru="Пространства",
                                label_en="Spaces",
                            ),
                            GuidedIntegrationLink(
                                href=f"/crm/settings/spaces/{quote(ns, safe='')}",
                                label_ru=f"Пространство «{ns}»",
                                label_en=f"Space «{ns}»",
                            ),
                            GuidedIntegrationLink(
                                href="/crm/settings/templates",
                                label_ru="Шаблоны пространств",
                                label_en="Space templates",
                            ),
                        ),
                    )
                _ = await repo.clone_entity_type_between_namespaces(
                    type_id,
                    source_namespace="default",
                    target_namespace=ns,
                    company_id=company_id,
                )
            extra = AMO_OPTIONAL_FIELDS_BY_TYPE_ID.get(type_id)
            if extra:
                await repo.merge_optional_fields_if_absent(
                    type_id,
                    namespace=ns,
                    company_id=company_id,
                    extra=extra,
                )
        await self._namespace_template_service.ensure_core_workspace_types_linked_to_namespace(ns)

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
        existing = await self._namespace_repository.get(namespace_name)
        if existing is None or existing.company_id != credential.company_id:
            return
        await self.ensure_namespace_ready(
            namespace_name=namespace_name,
            company_id=credential.company_id,
        )
        prev = existing.crm_settings
        integ_prev = dict(prev.integrations) if prev is not None else {}
        amo_prev = (
            dict(integ_prev.get("amocrm") or {})
            if isinstance(integ_prev.get("amocrm"), dict)
            else {}
        )
        if amo_prev.get("subdomain") == sub:
            return
        base = prev if prev is not None else NamespaceCRMSettings()
        integ = dict(base.integrations)
        amo = dict(integ.get("amocrm") or {}) if isinstance(integ.get("amocrm"), dict) else {}
        amo["subdomain"] = sub
        integ["amocrm"] = amo
        existing.crm_settings = base.model_copy(update={"integrations": integ})
        _ = await self._namespace_repository.set(existing)

    async def manifest_item(
        self,
        *,
        namespace_name: str,
        company_id: str,
        user_id: str,
        crm_settings: NamespaceCRMSettings | None,
    ) -> JsonObject:
        display: str | None = None
        if crm_settings is not None:
            block = self._as_json_object(type_cast(object, crm_settings.integrations.get("amocrm")))
            if block is not None:
                raw = block.get("subdomain")
                if isinstance(raw, str) and raw.strip():
                    display = raw.strip()
        cred = await self._oauth_service.get_valid_token(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.AMOCRM,
            service=f"amocrm:{namespace_name}",
        )
        connected = cred is not None
        out: JsonObject = {
            "provider_id": self.provider_id,
            "connected": connected,
            "display": display,
        }
        if crm_settings is not None:
            block = self._as_json_object(type_cast(object, crm_settings.integrations.get("amocrm")))
            if block is not None:
                if "auto_sync_enabled" in block:
                    out["auto_sync_enabled"] = bool(block.get("auto_sync_enabled"))
                ac = block.get("auto_sync_cron")
                if isinstance(ac, str) and ac.strip():
                    out["auto_sync_cron"] = ac.strip()
                atz = block.get("auto_sync_timezone")
                if isinstance(atz, str) and atz.strip():
                    out["auto_sync_timezone"] = atz.strip()
                sid = block.get("auto_sync_schedule_task_id")
                if isinstance(sid, str) and sid.strip():
                    out["auto_sync_schedule_task_id"] = sid.strip()
                if "auto_note_ai_analyze" in block:
                    out["auto_note_ai_analyze"] = bool(block.get("auto_note_ai_analyze"))
        return out
