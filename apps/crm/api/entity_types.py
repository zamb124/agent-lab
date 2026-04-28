"""
API для работы с типами entities.
"""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.pagination import OffsetPage
from apps.crm.models.api import EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.dependencies import ContainerDep
from apps.crm.db.models import EntityType
from apps.crm.color_palette import assign_color_from_palette
from apps.crm.entity_type_list_filter import resolve_list_entity_query_pair
from core.context import get_context

router = APIRouter(prefix="/entity-types", tags=["EntityTypes"])


class AddNamespaceIdsRequest(BaseModel):
    """Атомарное добавление namespace_ids к entity type."""
    namespace_ids: List[str]


class UpdatePublicFieldsRequest(BaseModel):
    """Запрос на обновление публичных полей"""
    public_fields: List[str]


async def _backfill_missing_colors(
    types: List[EntityType],
    repo: EntityTypeRepository,
) -> bool:
    used_colors = {
        entity_type.color
        for entity_type in types
        if isinstance(entity_type.color, str) and entity_type.color.strip()
    }
    updated = False
    for entity_type in types:
        if isinstance(entity_type.color, str) and entity_type.color.strip():
            continue
        assigned_color = assign_color_from_palette(used_colors)
        used_colors.add(assigned_color)
        await repo.update_color(entity_type.type_id, assigned_color)
        updated = True
    return updated


async def _collect_company_types(repo: EntityTypeRepository) -> list[EntityType]:
    page_limit = 200
    offset = 0
    items: list[EntityType] = []
    while True:
        page = await repo.get_all_for_company(limit=page_limit, offset=offset)
        if not page:
            return items
        items.extend(page)
        if len(page) < page_limit:
            return items
        offset += page_limit


def _entity_type_to_response(entity: EntityType, parent_map: dict[str, Optional[str]]) -> EntityTypeResponse:
    lt, ls = resolve_list_entity_query_pair(entity.type_id, parent_map)
    return EntityTypeResponse(
        type_id=entity.type_id,
        company_id=entity.company_id,
        parent_type_id=entity.parent_type_id,
        name=entity.name,
        description=entity.description,
        prompt=entity.prompt,
        required_fields=entity.required_fields,
        optional_fields=entity.optional_fields,
        public_fields=entity.public_fields,
        icon=entity.icon,
        color=entity.color,
        is_system=entity.is_system,
        is_event=entity.is_event,
        check_duplicates=entity.check_duplicates,
        weight_coefficient=entity.weight_coefficient,
        namespace_ids=entity.namespace_ids,
        is_context_anchor=entity.is_context_anchor,
        is_voice_target=entity.is_voice_target,
        extractable=entity.extractable,
        created_at=entity.created_at,
        list_entity_type=lt,
        list_entity_subtype=ls,
    )


@router.get("", response_model=OffsetPage[EntityTypeResponse])
async def list_entity_types(
    container: ContainerDep,
    namespace: Optional[str] = Query(default=None, description="Фильтр разрешенных типов по namespace"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[EntityTypeResponse]:
    repo = container.entity_type_repository
    types, total, parent_map = await asyncio.gather(
        repo.get_all_for_company(namespace=namespace, limit=limit, offset=offset),
        repo.count_all_for_company(namespace=namespace),
        repo.get_parent_type_id_map_for_company(),
    )
    if await _backfill_missing_colors(types, repo):
        types = await repo.get_all_for_company(namespace=namespace, limit=limit, offset=offset)
    items = [_entity_type_to_response(t, parent_map) for t in types]
    return OffsetPage[EntityTypeResponse](items=items, total=total, limit=limit, offset=offset)


@router.get("/by-namespace/{namespace}", response_model=OffsetPage[EntityTypeResponse])
async def list_entity_types_by_namespace(
    namespace: str,
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[EntityTypeResponse]:
    normalized_namespace = namespace.strip()
    if not normalized_namespace:
        raise HTTPException(status_code=422, detail="namespace is required")
    repo = container.entity_type_repository
    types, total, parent_map = await asyncio.gather(
        repo.get_all_for_company(namespace=normalized_namespace, limit=limit, offset=offset),
        repo.count_all_for_company(normalized_namespace),
        repo.get_parent_type_id_map_for_company(),
    )
    if await _backfill_missing_colors(types, repo):
        types = await repo.get_all_for_company(namespace=normalized_namespace, limit=limit, offset=offset)
    items = [_entity_type_to_response(t, parent_map) for t in types]
    return OffsetPage[EntityTypeResponse](items=items, total=total, limit=limit, offset=offset)


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    container: ContainerDep,
):
    """Получить тип entity по ID"""
    repo = container.entity_type_repository
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    if not entity_type.color or not entity_type.color.strip():
        assigned_color = assign_color_from_palette(set())
        await repo.update_color(type_id, assigned_color)
        entity_type.color = assigned_color
    parent_map = await repo.get_parent_type_id_map_for_company()
    return _entity_type_to_response(entity_type, parent_map)


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    data: EntityTypeCreate,
    container: ContainerDep,
):
    """Создать новый тип entity"""
    repo = container.entity_type_repository
    context = get_context()
    company_id = context.active_company.company_id
    namespace_ids = data.namespace_ids or ["default"]
    if len(namespace_ids) == 0:
        raise HTTPException(status_code=422, detail="namespace_ids must not be empty")

    existing_types = await _collect_company_types(repo)
    used_colors = {
        et.color for et in existing_types
        if isinstance(et.color, str) and et.color.strip()
    }
    resolved_color = data.color
    if not resolved_color or not resolved_color.strip():
        resolved_color = assign_color_from_palette(used_colors)

    entity_type = EntityType(
        type_id=data.type_id,
        name=data.name,
        description=data.description,
        parent_type_id=data.parent_type_id,
        prompt=data.prompt,
        required_fields=data.required_fields or {},
        optional_fields=data.optional_fields or {},
        icon=data.icon,
        color=resolved_color,
        is_system=False,
        is_event=data.is_event,
        check_duplicates=data.check_duplicates,
        namespace_ids=namespace_ids,
        company_id=company_id,
        is_context_anchor=data.is_context_anchor,
        is_voice_target=data.is_voice_target,
    )
    
    await repo.create_custom_type(entity_type, company_id)
    parent_map = await repo.get_parent_type_id_map_for_company()
    refreshed = await repo.get_by_type_id(data.type_id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="EntityType not found after create")
    return _entity_type_to_response(refreshed, parent_map)


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    data: EntityTypeUpdate,
    container: ContainerDep,
):
    """Обновить тип entity"""
    repo = container.entity_type_repository
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")

    fields: dict = {}
    if data.name is not None:
        fields["name"] = data.name
    if data.description is not None:
        fields["description"] = data.description
    if data.parent_type_id is not None:
        fields["parent_type_id"] = data.parent_type_id
    if data.prompt is not None:
        fields["prompt"] = data.prompt
    if data.required_fields is not None:
        fields["required_fields"] = data.required_fields
    if data.optional_fields is not None:
        fields["optional_fields"] = data.optional_fields
    if data.icon is not None:
        fields["icon"] = data.icon
    if data.color is not None:
        fields["color"] = data.color
    if data.is_context_anchor is not None:
        fields["is_context_anchor"] = data.is_context_anchor
    if data.is_voice_target is not None:
        fields["is_voice_target"] = data.is_voice_target

    resolved_color = fields.get("color") or entity_type.color
    if not resolved_color or not resolved_color.strip():
        fields["color"] = assign_color_from_palette(set())

    if fields:
        await repo.update_metadata(type_id, **fields)

    if data.namespace_ids is not None:
        if len(data.namespace_ids) == 0:
            raise HTTPException(status_code=422, detail="namespace_ids must not be empty")
        entity_type = await repo.set_namespace_ids(type_id, data.namespace_ids)
    elif fields:
        entity_type = await repo.get_by_type_id(type_id)

    parent_map = await repo.get_parent_type_id_map_for_company()
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    return _entity_type_to_response(entity_type, parent_map)


@router.post("/{type_id}/namespaces", response_model=EntityTypeResponse)
async def add_namespace_ids(
    type_id: str,
    data: AddNamespaceIdsRequest,
    container: ContainerDep,
):
    """Атомарно добавляет namespace_ids к entity type (SELECT FOR UPDATE)."""
    if not data.namespace_ids:
        raise HTTPException(status_code=422, detail="namespace_ids must not be empty")
    repo = container.entity_type_repository
    try:
        updated = await repo.add_namespace_ids(type_id, data.namespace_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    parent_map = await repo.get_parent_type_id_map_for_company()
    return _entity_type_to_response(updated, parent_map)


@router.put("/{type_id}/public-fields", response_model=EntityTypeResponse)
async def update_public_fields(
    type_id: str,
    data: UpdatePublicFieldsRequest,
    container: ContainerDep,
):
    """Обновить список публичных полей для типа"""
    repo = container.entity_type_repository
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")

    await repo.update_metadata(type_id, public_fields=data.public_fields)

    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    parent_map = await repo.get_parent_type_id_map_for_company()
    return _entity_type_to_response(entity_type, parent_map)
