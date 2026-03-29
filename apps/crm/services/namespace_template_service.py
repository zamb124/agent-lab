"""Сервис для CRUD шаблонов namespace и их применения."""

from typing import Optional

from core.context import get_context
from core.models.identity_models import Namespace

from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from core.db.repositories.namespace_repository import NamespaceRepository


class NamespaceTemplateService:
    def __init__(
        self,
        template_repo: NamespaceTemplateRepository,
        entity_type_repo: EntityTypeRepository,
        namespace_repo: NamespaceRepository,
    ) -> None:
        self._template_repo = template_repo
        self._entity_type_repo = entity_type_repo
        self._namespace_repo = namespace_repo

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
                )
                runtime_type = await self._entity_type_repo.create(runtime_type)
                existing_types_map[runtime_type.type_id] = runtime_type

            current_namespaces = list(runtime_type.namespace_ids or [])
            if namespace_name not in current_namespaces:
                current_namespaces.append(namespace_name)
                runtime_type.namespace_ids = current_namespaces
                await self._entity_type_repo.update(runtime_type)

        return namespace
