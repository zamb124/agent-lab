"""Сервис для CRUD шаблонов namespace и их применения."""

from typing import Any, Optional

from core.context import get_context
from core.models.identity_models import Namespace

from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from core.db.repositories.namespace_repository import NamespaceRepository


class NamespaceTemplateService:
    def __init__(
        self,
        template_repo: NamespaceTemplateRepository,
        entity_type_repo: EntityTypeRepository,
        namespace_repo: NamespaceRepository,
        entity_repo: EntityRepository,
    ) -> None:
        self._template_repo = template_repo
        self._entity_type_repo = entity_type_repo
        self._namespace_repo = namespace_repo
        self._entity_repo = entity_repo

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

        template_types = await self._template_repo.list_types(template.template_key)
        if not template_types:
            raise ValueError(f"Template {template_id} has no types")

        namespace = Namespace(
            name=namespace_name,
            company_id=company_id,
            description=namespace_description,
            is_default=False,
        )
        await self._namespace_repo.set(namespace)

        existing_types = await self._entity_type_repo.get_all_for_company()
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
                )
                runtime_type = await self._entity_type_repo.create(runtime_type)
                existing_types_map[runtime_type.type_id] = runtime_type

            current_namespaces = runtime_type.namespace_ids or []
            if namespace_name not in current_namespaces:
                await self._entity_type_repo.add_namespace_ids(
                    runtime_type.type_id, [namespace_name],
                )

        return namespace

    async def get_namespace_editability(self, namespace_name: str) -> dict[str, Any]:
        entity_count = await self._entity_repo.count_by_namespace(namespace_name)
        used_type_ids = await self._entity_repo.list_used_entity_types_by_namespace(namespace_name)
        used_type_ids_set = set(used_type_ids)

        all_types = await self._entity_type_repo.get_all_for_company()
        current_allowed_type_ids = sorted(
            [item.type_id for item in all_types if namespace_name in (item.namespace_ids or [])]
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
            "used_type_ids": used_type_ids,
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
            requested_set = set(allowed_type_ids)
            missing_locked = locked_type_ids - requested_set
            if missing_locked:
                raise ValueError(
                    f"Нельзя убрать типы с существующими сущностями: {', '.join(sorted(missing_locked))}"
                )

            current_allowed_type_ids = set(editability["current_allowed_type_ids"])
            if requested_set != current_allowed_type_ids:
                all_types = await self._entity_type_repo.get_all_for_company()
                for item in all_types:
                    current_ns = set(item.namespace_ids or [])
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
