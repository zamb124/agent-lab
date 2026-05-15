"""Сервис для CRUD шаблонов namespace и их применения."""

from typing import Any

from apps.crm.constants_graph import (
    ENTITY_TYPES_CLONED_INTO_NEW_NAMESPACE,
    ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
    NOTE_ROOT_ENTITY_TYPE_ID,
    TASK_ROOT_ENTITY_TYPE_ID,
)
from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_CORE_NOTE_TASK,
    REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS,
)
from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
from core.models.identity_models import Namespace, NamespaceCRMSettings


class NamespaceTemplateService:
    _PAGE_LIMIT = 200

    def __init__(
        self,
        template_repo: NamespaceTemplateRepository,
        entity_type_repo: EntityTypeRepository,
        namespace_repo: NamespaceRepository,
        entity_repo: EntityRepository,
        company_init_service: CompanyInitService,
    ) -> None:
        self._template_repo = template_repo
        self._entity_type_repo = entity_type_repo
        self._namespace_repo = namespace_repo
        self._entity_repo = entity_repo
        self._company_init_service = company_init_service

    @staticmethod
    def _get_company_id() -> str:
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    async def _load_company_types(self) -> list[EntityType]:
        items: list[EntityType] = []
        offset = 0
        while True:
            page = await self._entity_type_repo.get_all_for_company(
                limit=self._PAGE_LIMIT,
                offset=offset,
            )
            if not page:
                return items
            items.extend(page)
            if len(page) < self._PAGE_LIMIT:
                return items
            offset += self._PAGE_LIMIT

    async def _ensure_template_db_core_note_task_rows(self, template_key: str) -> None:
        """Идемпотентно добавляет в шаблон строки note и task, если их ещё нет."""
        existing = await self._template_repo.list_types(template_key)
        present = {t.type_id for t in existing}
        for row in NAMESPACE_TEMPLATE_CORE_NOTE_TASK:
            tid = row["type_id"]
            if not isinstance(tid, str) or len(tid) == 0:
                raise ValueError("NAMESPACE_TEMPLATE_CORE_NOTE_TASK: type_id required")
            if tid in present:
                continue
            await self._template_repo.upsert_type(
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
        final_ids = {t.type_id for t in await self._template_repo.list_types(template_key)}
        missing = REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS - final_ids
        if missing:
            raise ValueError(
                "Шаблон пространства обязан содержать типы note и task; "
                f"в шаблоне отсутствуют: {', '.join(sorted(missing))}"
            )

    async def _materialize_entity_type_row(
        self,
        *,
        company_id: str,
        target_namespace: str,
        item: Any,
        is_system: bool,
    ) -> EntityType:
        row = await self._entity_type_repo.get_by_type_id(
            item.type_id,
            namespace=target_namespace,
            company_id=company_id,
        )
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
            return await self._entity_type_repo.create(entity_type)
        await self._entity_type_repo.update_metadata(
            item.type_id,
            namespace=target_namespace,
            company_id=company_id,
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
        refreshed = await self._entity_type_repo.get_by_type_id(
            item.type_id,
            namespace=target_namespace,
            company_id=company_id,
        )
        if refreshed is None:
            raise ValueError(
                f"EntityType {item.type_id!r} не найден после update_metadata "
                f"в пространстве {target_namespace!r}"
            )
        return refreshed

    async def ensure_core_workspace_types_linked_to_namespace(self, namespace_name: str) -> None:
        """
        Гарантирует типы note и task в пространстве: при отсутствии строки — копия из default.
        """
        name = namespace_name.strip()
        if not name:
            raise ValueError("namespace_name is required")
        company_id = self._get_company_id()
        for tid in (NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID):
            row = await self._entity_type_repo.get_by_type_id(
                tid, namespace=name, company_id=company_id,
            )
            if row is not None:
                continue
            await self._entity_type_repo.clone_entity_type_between_namespaces(
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
        row = await self._entity_type_repo.get_by_type_id(
            type_id,
            namespace=target_namespace,
            company_id=company_id,
        )
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
                f"Тип сущности {type_id!r} не найден ни в одном пространстве компании. "
                "Добавьте тип в каталоге или через шаблон пространства."
            )
        await self._entity_type_repo.clone_entity_type_between_namespaces(
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
            existing = await self._entity_type_repo.get_by_type_id(
                tid, namespace=target_namespace, company_id=company_id,
            )
            if existing is not None:
                continue
            await self._entity_type_repo.clone_entity_type_between_namespaces(
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

        existing_namespace = await self._namespace_repo.get(namespace_name)
        if existing_namespace:
            raise ValueError(f"Namespace {namespace_name} already exists")

        template = await self._template_repo.get_by_template_id(template_id)
        if template is None:
            raise ValueError(f"Template {template_id} not found")

        await self._ensure_template_db_core_note_task_rows(template.template_key)

        template_types = await self._template_repo.list_types(template.template_key)
        if not template_types:
            raise ValueError(f"Template {template_id} has no types")

        namespace = Namespace(
            name=namespace_name,
            company_id=company_id,
            description=namespace_description,
            is_default=False,
        )
        raw_tpl_crm = getattr(template, "crm_settings", None)
        if raw_tpl_crm is not None and isinstance(raw_tpl_crm, dict) and len(raw_tpl_crm) > 0:
            namespace.crm_settings = NamespaceCRMSettings.model_validate(raw_tpl_crm)
        await self._namespace_repo.set(namespace)

        for item in template_types:
            await self._materialize_entity_type_row(
                company_id=company_id,
                target_namespace=namespace_name,
                item=item,
                is_system=False,
            )

        await self.ensure_core_workspace_types_linked_to_namespace(namespace_name)
        await self._ensure_platform_types_in_namespace(
            company_id=company_id,
            target_namespace=namespace_name,
        )

        await self._company_init_service._ensure_namespace_entity(company_id, namespace_name)

        return namespace

    async def get_namespace_editability(self, namespace_name: str) -> dict[str, Any]:
        types_here = await self._entity_type_repo.get_all_for_company(
            namespace=namespace_name, include_system=True, limit=10_000, offset=0,
        )
        current_allowed_type_ids = sorted({t.type_id for t in types_here})

        type_ids_elsewhere: set[str] = set()
        for row in await self._load_company_types():
            if row.namespace != namespace_name:
                type_ids_elsewhere.add(row.type_id)
        addable_type_ids = sorted(type_ids_elsewhere - set(current_allowed_type_ids))

        entity_count = await self._entity_repo.count_by_namespace(
            namespace_name,
            exclude_entity_types=ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
        )
        used_type_ids = await self._entity_repo.list_used_entity_types_by_namespace(
            namespace_name,
            exclude_entity_types=ENTITY_TYPES_EXCLUDED_FROM_NAMESPACE_EDITABILITY_COUNTS,
        )
        used_type_ids_set = set(used_type_ids)

        locked_type_ids = sorted(used_type_ids_set)
        removable_type_ids = sorted(
            tid for tid in current_allowed_type_ids if tid not in used_type_ids_set
        )

        has_entities = entity_count > 0

        return {
            "namespace": namespace_name,
            "has_entities": has_entities,
            "entity_count": entity_count,
            "used_type_ids": sorted(used_type_ids_set),
            "current_allowed_type_ids": current_allowed_type_ids,
            "can_update_allowed_types": not has_entities,
            "can_add_types": True,
            "locked_type_ids": locked_type_ids,
            "removable_type_ids": removable_type_ids,
            "all_spaces_type_ids": addable_type_ids,
            "lock_reason": None,
        }

    async def update_existing_namespace(
        self,
        namespace_name: str,
        description_is_set: bool,
        description: str | None,
        allowed_type_ids: list[str] | None,
    ) -> Namespace:
        namespace = await self._namespace_repo.get(namespace_name)
        if namespace is None:
            raise RuntimeError(f"Namespace {namespace_name} not found")

        company_id = self._get_company_id()

        if allowed_type_ids is not None:
            editability = await self.get_namespace_editability(namespace_name)
            locked_type_ids = set(editability["locked_type_ids"])
            requested_set = await self.expanded_allowed_type_ids_for_namespace_update(
                allowed_type_ids
            )
            missing_locked = locked_type_ids - requested_set
            if missing_locked:
                raise ValueError(
                    f"Нельзя убрать типы с существующими сущностями: {', '.join(sorted(missing_locked))}"
                )

            current_allowed_type_ids = set(editability["current_allowed_type_ids"])
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
                    await self._entity_type_repo.delete_entity_type_scoped(
                        type_id,
                        namespace=namespace_name,
                        company_id=company_id,
                    )

        if description_is_set:
            namespace.description = description
            await self._namespace_repo.set(namespace)

        return namespace
