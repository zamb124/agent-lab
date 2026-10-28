"""Сервис для CRUD шаблонов namespace и их применения."""

from typing import ClassVar

from oxyde.exceptions import UniqueViolationError

from apps.crm.constants_graph import (
    ENTITY_TYPES_CLONED_INTO_NEW_NAMESPACE,
    ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
    NOTE_ROOT_ENTITY_TYPE_ID,
    TASK_ROOT_ENTITY_TYPE_ID,
)
from apps.crm.models.api import NamespaceEditabilityResponse
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.entity_type import EntityType
from apps.crm.models.namespace_template import NamespaceTemplate
from apps.crm.models.namespace_template_type import NamespaceTemplateType
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_CORE_NOTE_TASK,
    REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS,
)
from apps.crm_worker.tasks.task_names import CRM_GENERATE_NAMESPACE_SUGGESTS
from core.clients.scheduler_client import SchedulerClient
from core.context import get_context
from core.errors.boundary import PlatformNotFoundError
from core.models.identity_models import Namespace, NamespaceCRMSettings
from core.namespace import NamespaceService
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleType


class NamespaceTemplateService:
    _PAGE_LIMIT: ClassVar[int] = 200

    def __init__(
        self,
        namespace_service: NamespaceService,
        company_init_service: CompanyInitService,
        scheduler_client: SchedulerClient,
    ) -> None:
        self._namespace_service: NamespaceService = namespace_service
        self._company_init_service: CompanyInitService = company_init_service
        self._scheduler_client: SchedulerClient = scheduler_client

    @staticmethod
    def _get_company_id() -> str:
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError("No active company in context")
        return context.active_company.company_id

    async def _load_company_types(self) -> list[EntityType]:
        return await EntityType.catalog()

    async def _ensure_template_db_core_note_task_rows(self, template_key: str) -> None:
        """Идемпотентно добавляет в шаблон строки note и task, если их ещё нет."""
        existing = await NamespaceTemplateType.list_for_template(template_key)
        present = {t.type_id for t in existing}
        for row in NAMESPACE_TEMPLATE_CORE_NOTE_TASK:
            tid = row["type_id"]
            if len(tid) == 0:
                raise ValueError("NAMESPACE_TEMPLATE_CORE_NOTE_TASK: type_id required")
            if tid in present:
                continue
            _ = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
                template_key=template_key,
                type_id=tid,
                parent_type_id=row.get("parent_type_id"),
                name=row["name"],
                description=row.get("description"),
                prompt=row.get("prompt"),
                required_fields=row.get("required_fields") or {},
                optional_fields=row.get("optional_fields") or {},
                icon=row.get("icon"),
                color=row.get("color"),
                is_event=bool(row.get("is_event", False)),
                check_duplicates=bool(row.get("check_duplicates", True)),
                weight_coefficient=float(row.get("weight_coefficient", 1.0)),
                namespace_ids=list(row.get("namespace_ids") or []),
                is_context_anchor=bool(row.get("is_context_anchor", False)),
                is_voice_target=bool(row.get("is_voice_target", False)),
            )
        final_ids = {t.type_id for t in await NamespaceTemplateType.list_for_template(template_key)}
        missing = REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS - final_ids
        if missing:
            raise ValueError(
                f"Namespace template must contain note and task types; missing: {', '.join(sorted(missing))}"
            )

    async def _materialize_entity_type_row(
        self,
        *,
        company_id: str,
        target_namespace: str,
        item: NamespaceTemplateType,
        is_system: bool,
    ) -> EntityType:
        row = await EntityType.by_company_namespace_and_type_id(
            company_id=company_id,
            namespace=target_namespace,
            type_id=item.type_id,
        ).get_or_none()
        if row is None:
            entity_type = EntityType(
                type_id=item.type_id,
                company_id=company_id,
                namespace=target_namespace,
                parent_type_id=item.parent_type_id,
                name=item.name,
                description=item.description,
                prompt=item.prompt,
                required_fields=item.required_fields,
                optional_fields=item.optional_fields,
                icon=item.icon,
                color=item.color,
                is_system=is_system,
                is_event=item.is_event,
                check_duplicates=item.check_duplicates,
                weight_coefficient=item.weight_coefficient,
                is_context_anchor=item.is_context_anchor,
                is_voice_target=item.is_voice_target,
            )
            try:
                return await EntityType.create(entity_type)
            except UniqueViolationError:
                raced = await EntityType.by_company_namespace_and_type_id(
                    company_id=company_id,
                    namespace=target_namespace,
                    type_id=item.type_id,
                ).get_or_none()
                if raced is None:
                    raise
                row = raced
        await EntityType.update_field_patch(
            item.type_id,
            namespace=target_namespace,
            company_id=company_id,
            patch={
                "parent_type_id": item.parent_type_id,
                "name": item.name,
                "description": item.description,
                "prompt": item.prompt,
                "required_fields": item.required_fields,
                "optional_fields": item.optional_fields,
                "icon": item.icon,
                "color": item.color,
                "is_system": is_system,
                "is_event": item.is_event,
                "check_duplicates": item.check_duplicates,
                "weight_coefficient": item.weight_coefficient,
                "is_context_anchor": item.is_context_anchor,
                "is_voice_target": item.is_voice_target,
            },
        )
        refreshed = await EntityType.by_company_namespace_and_type_id(
            company_id=company_id,
            namespace=target_namespace,
            type_id=item.type_id,
        ).get_or_none()
        if refreshed is None:
            raise ValueError(
                f"EntityType {item.type_id!r} not found after update_metadata in namespace {target_namespace!r}"
            )
        return refreshed

    async def ensure_core_namespace_types_linked_to_namespace(self, namespace_name: str) -> None:
        """
        Гарантирует типы note и task в namespace: при отсутствии строки — копия из default.
        """
        name = namespace_name.strip()
        if not name:
            raise ValueError("namespace_name is required")
        company_id = self._get_company_id()
        for tid in (NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID):
            row = await EntityType.by_company_namespace_and_type_id(
                company_id=company_id,
                namespace=name,
                type_id=tid,
            ).get_or_none()
            if row is not None:
                continue
            _ = await EntityType.ensure_in_namespace(
                tid,
                source_namespace="default",
                target_namespace=name,
                company_id=company_id,
            )

    async def _clone_type_into_namespace_if_missing(
        self,
        type_id: str,
        target_namespace: str,
        company_id: str,
    ) -> None:
        row = await EntityType.by_company_namespace_and_type_id(
            company_id=company_id,
            namespace=target_namespace,
            type_id=type_id,
        ).get_or_none()
        if row is not None:
            return
        source_ns: str | None = None
        for item in await self._load_company_types():
            if item.company_id != company_id:
                continue
            if item.namespace == target_namespace:
                continue
            if item.type_id == type_id:
                source_ns = item.namespace
                break
        if source_ns is None:
            raise ValueError(
                f"Entity type {type_id!r} was not found in any company namespace. Add the type in the catalog or via a namespace template."
            )
        _ = await EntityType.ensure_in_namespace(
            type_id,
            source_namespace=source_ns,
            target_namespace=target_namespace,
            company_id=company_id,
        )

    async def _ensure_platform_types_in_namespace(
        self,
        *,
        company_id: str,
        target_namespace: str,
    ) -> None:
        if target_namespace == "default":
            return
        for tid in sorted(ENTITY_TYPES_CLONED_INTO_NEW_NAMESPACE):
            existing = await EntityType.by_company_namespace_and_type_id(
                company_id=company_id,
                namespace=target_namespace,
                type_id=tid,
            ).get_or_none()
            if existing is not None:
                continue
            _ = await EntityType.ensure_in_namespace(
                tid,
                source_namespace="default",
                target_namespace=target_namespace,
                company_id=company_id,
            )

    async def expanded_allowed_type_ids_for_namespace_update(
        self, allowed_type_ids: list[str]
    ) -> set[str]:
        """Множество типов при сохранении списка разрешённых (корни note и task не снимаются)."""
        return set(allowed_type_ids) | {NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID}

    async def create_namespace_from_template(
        self,
        namespace_name: str,
        namespace_description: str | None,
        template_id: str,
    ) -> Namespace:
        company_id = self._get_company_id()

        existing_namespace = await self._namespace_service.get(namespace_name)
        if existing_namespace:
            raise ValueError(f"Namespace {namespace_name} already exists")

        template = await NamespaceTemplate.by_template_id(company_id, template_id)
        if template is None:
            raise ValueError(f"Template {template_id} not found")

        await self._ensure_template_db_core_note_task_rows(template.template_key)

        template_types = await NamespaceTemplateType.list_for_template(template.template_key)
        if not template_types:
            raise ValueError(f"Template {template_id} has no types")

        template_crm_settings: NamespaceCRMSettings | None = None
        raw_tpl_crm = template.crm_settings
        if raw_tpl_crm is not None and len(raw_tpl_crm) > 0:
            template_crm_settings = NamespaceCRMSettings.model_validate(raw_tpl_crm)
        namespace = await self._namespace_service.create(
            name=namespace_name,
            description=namespace_description,
            is_default=False,
            crm_settings=template_crm_settings,
        )

        for item in template_types:
            _ = await self._materialize_entity_type_row(
                company_id=company_id,
                target_namespace=namespace_name,
                item=item,
                is_system=False,
            )

        await self.ensure_core_namespace_types_linked_to_namespace(namespace_name)
        await self._ensure_platform_types_in_namespace(
            company_id=company_id,
            target_namespace=namespace_name,
        )

        _ = await self._company_init_service.ensure_namespace_entity(company_id, namespace_name)

        return namespace

    async def get_namespace_editability(self, namespace_name: str) -> NamespaceEditabilityResponse:
        types_here = await EntityType.catalog(
            namespace=namespace_name
        )
        current_allowed_type_ids = sorted({t.type_id for t in types_here})

        type_ids_elsewhere: set[str] = set()
        for row in await self._load_company_types():
            if row.namespace != namespace_name:
                type_ids_elsewhere.add(row.type_id)
        addable_type_ids = sorted(type_ids_elsewhere - set(current_allowed_type_ids))

        entity_count = await CRMEntity.count_for_namespace(
            namespace_name,
            exclude_entity_types=ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
        )
        used_type_ids = await CRMEntity.list_entity_type_ids_for_namespace(
            namespace_name,
            exclude_entity_types=ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
        )
        used_type_ids_set = set(used_type_ids)

        locked_type_ids = sorted(used_type_ids_set)
        removable_type_ids = sorted(
            tid for tid in current_allowed_type_ids if tid not in used_type_ids_set
        )

        has_entities = entity_count > 0

        return NamespaceEditabilityResponse(
            namespace=namespace_name,
            has_entities=has_entities,
            entity_count=entity_count,
            used_type_ids=sorted(used_type_ids_set),
            current_allowed_type_ids=current_allowed_type_ids,
            can_update_allowed_types=not has_entities,
            can_add_types=True,
            locked_type_ids=locked_type_ids,
            removable_type_ids=removable_type_ids,
            all_namespaces_type_ids=addable_type_ids,
            lock_reason=None,
        )

    async def update_existing_namespace(
        self,
        namespace_name: str,
        description_is_set: bool,
        description: str | None,
        allowed_type_ids: list[str] | None,
    ) -> Namespace:
        namespace = await self._namespace_service.get(namespace_name)
        if namespace is None:
            raise RuntimeError(f"Namespace {namespace_name} not found")

        company_id = self._get_company_id()

        if allowed_type_ids is not None:
            editability = await self.get_namespace_editability(namespace_name)
            locked_type_ids = set(editability.locked_type_ids)
            requested_set = await self.expanded_allowed_type_ids_for_namespace_update(
                allowed_type_ids
            )
            missing_locked = locked_type_ids - requested_set
            if missing_locked:
                raise ValueError(
                    f"Cannot remove types that still have entities: {', '.join(sorted(missing_locked))}"
                )

            current_allowed_type_ids = set(editability.current_allowed_type_ids)
            if requested_set != current_allowed_type_ids:
                for type_id in sorted(requested_set - current_allowed_type_ids):
                    await self._clone_type_into_namespace_if_missing(
                        type_id,
                        namespace_name,
                        company_id,
                    )
                for type_id in sorted(current_allowed_type_ids - requested_set):
                    if type_id in {
                        NOTE_ROOT_ENTITY_TYPE_ID,
                        TASK_ROOT_ENTITY_TYPE_ID,
                    }:
                        continue
                    _ = await EntityType.delete_by_company_namespace_and_type_id(
                        type_id,
                        namespace=namespace_name,
                        company_id=company_id,
                    )

        if description_is_set:
            namespace.description = description
            _ = await self._namespace_service.save(namespace)

        return namespace

    async def apply_namespace_crm_settings(
        self,
        namespace_name: str,
        incoming: NamespaceCRMSettings,
    ) -> Namespace:
        ns = await self._namespace_service.get(namespace_name)
        if ns is None:
            raise PlatformNotFoundError(
                f"Namespace {namespace_name} not found", error_code="not_found"
            )
        prev = ns.crm_settings or NamespaceCRMSettings()
        data = prev.model_dump()
        for field_name in incoming.model_fields_set:
            data[field_name] = getattr(incoming, field_name)
        new_settings = NamespaceCRMSettings.model_validate(data)
        if "suggests" in incoming.model_fields_set:
            if prev.suggests.schedule_task_id:
                _ = await self._scheduler_client.cancel_schedule(prev.suggests.schedule_task_id)
            new_settings.suggests.schedule_task_id = None
            if new_settings.suggests.enabled:
                created = await self._scheduler_client.create_schedule(
                    PlatformScheduleCreateRequest(
                        target_service="crm",
                        task_name=CRM_GENERATE_NAMESPACE_SUGGESTS.name,
                        queue_name="crm",
                        schedule_type=PlatformScheduleType.CRON,
                        cron=new_settings.suggests.cron,
                        payload={"company_id": ns.company_id, "namespace": namespace_name},
                    )
                )
                new_settings.suggests.schedule_task_id = created.schedule_task_id
        ns.crm_settings = new_settings
        return await self._namespace_service.save(ns)
