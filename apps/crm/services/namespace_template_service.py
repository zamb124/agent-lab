"""Сервис для CRUD шаблонов namespace и их применения."""

from typing import Any, Optional

from core.context import get_context
from core.models.identity_models import Namespace, NamespaceCRMSettings

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID
from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_CORE_NOTE_TASK,
    REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS,
)
from core.db.repositories.namespace_repository import NamespaceRepository


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

    async def ensure_core_workspace_types_linked_to_namespace(self, namespace_name: str) -> None:
        """
        Корневые типы note и task привязаны к пространству.

        Подтипы task и подтипы заметок (meeting, call и др.) не подмешиваются: их добавляют шаблон или настройки типов.
        Без привязок note и task списки и сайдбар по разрешённым типам обрезаются.
        """
        name = namespace_name.strip()
        if not name:
            raise ValueError("namespace_name is required")
        all_types = await self._load_company_types()
        for tid in (NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID):
            row = next((t for t in all_types if t.type_id == tid), None)
            if row is None:
                raise ValueError(f"System entity type {tid!r} is required")
            if name not in row.namespace_ids_list():
                await self._entity_type_repo.add_namespace_ids(tid, [name])

    async def expanded_allowed_type_ids_for_namespace_update(
        self, allowed_type_ids: list[str]
    ) -> set[str]:
        """Множество типов при сохранении списка разрешённых (корни note и task не снимаются)."""
        return set(allowed_type_ids) | {NOTE_ROOT_ENTITY_TYPE_ID, TASK_ROOT_ENTITY_TYPE_ID}

    async def create_namespace_from_template(
        self,
        namespace_name: str,
        namespace_description: Optional[str],
        template_id: str,
    ) -> Namespace:
        context = get_context()
        company_id = context.active_company.company_id

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

        existing_types = await self._load_company_types()
        existing_types_map = {item.type_id: item for item in existing_types}

        for item in template_types:
            runtime_type = existing_types_map.get(item.type_id)
            if runtime_type is None:
                runtime_type = EntityType(
                    type_id=item.type_id,
                    company_id=company_id,
                    parent_type_id=item.parent_type_id,
                    name=item.name,
                    description=item.description,
                    prompt=item.prompt,
                    required_fields=item.required_fields,
                    optional_fields=item.optional_fields,
                    icon=item.icon,
                    color=item.color,
                    is_system=False,
                    is_event=item.is_event,
                    check_duplicates=item.check_duplicates,
                    weight_coefficient=item.weight_coefficient,
                    namespace_ids=[],
                    is_context_anchor=item.is_context_anchor,
                    is_voice_target=item.is_voice_target,
                )
                runtime_type = await self._entity_type_repo.update(runtime_type)
                existing_types_map[runtime_type.type_id] = runtime_type
            else:
                await self._entity_type_repo.update_metadata(
                    runtime_type.type_id,
                    company_id=company_id,
                    parent_type_id=item.parent_type_id,
                    name=item.name,
                    description=item.description,
                    prompt=item.prompt,
                    required_fields=item.required_fields,
                    optional_fields=item.optional_fields,
                    icon=item.icon,
                    color=item.color,
                    is_event=item.is_event,
                    check_duplicates=item.check_duplicates,
                    weight_coefficient=item.weight_coefficient,
                    is_context_anchor=item.is_context_anchor,
                    is_voice_target=item.is_voice_target,
                )

            current_namespaces = runtime_type.namespace_ids_list()
            if namespace_name not in current_namespaces:
                await self._entity_type_repo.add_namespace_ids(
                    runtime_type.type_id, [namespace_name],
                )

        await self.ensure_core_workspace_types_linked_to_namespace(namespace_name)

        await self._company_init_service._ensure_namespace_entity(company_id, namespace_name)

        return namespace

    async def get_namespace_editability(self, namespace_name: str) -> dict[str, Any]:
        all_types = await self._load_company_types()

        cross_namespace_type_ids = {
            t.type_id for t in all_types if "*" in t.namespace_ids_list()
        }

        entity_count = await self._entity_repo.count_by_namespace(
            namespace_name, exclude_entity_types=cross_namespace_type_ids,
        )
        used_type_ids = await self._entity_repo.list_used_entity_types_by_namespace(namespace_name)
        used_type_ids_set = set(used_type_ids) - cross_namespace_type_ids

        def _type_linked_to_namespace(row: EntityType) -> bool:
            ns = row.namespace_ids_list()
            return namespace_name in ns or "*" in ns

        current_allowed_type_ids = sorted(
            [item.type_id for item in all_types if _type_linked_to_namespace(item)]
        )

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
            "lock_reason": None,
        }

    async def update_existing_namespace(
        self,
        namespace_name: str,
        description_is_set: bool,
        description: Optional[str],
        allowed_type_ids: Optional[list[str]],
    ) -> Namespace:
        namespace = await self._namespace_repo.get(namespace_name)
        if namespace is None:
            raise RuntimeError(f"Namespace {namespace_name} not found")

        if allowed_type_ids is not None:
            editability = await self.get_namespace_editability(namespace_name)
            locked_type_ids = set(editability["locked_type_ids"])
            requested_set = await self.expanded_allowed_type_ids_for_namespace_update(allowed_type_ids)
            missing_locked = locked_type_ids - requested_set
            if missing_locked:
                raise ValueError(
                    f"Нельзя убрать типы с существующими сущностями: {', '.join(sorted(missing_locked))}"
                )

            current_allowed_type_ids = set(editability["current_allowed_type_ids"])
            if requested_set != current_allowed_type_ids:
                all_types = await self._load_company_types()
                for item in all_types:
                    current_ns = set(item.namespace_ids_list())
                    has_namespace = namespace_name in current_ns
                    should_have_namespace = item.type_id in requested_set
                    if has_namespace == should_have_namespace:
                        continue

                    if should_have_namespace:
                        await self._entity_type_repo.add_namespace_ids(
                            item.type_id, [namespace_name],
                        )
                    else:
                        await self._entity_type_repo.remove_namespace_ids(
                            item.type_id, [namespace_name],
                        )

        if description_is_set:
            namespace.description = description
            await self._namespace_repo.set(namespace)

        return namespace
