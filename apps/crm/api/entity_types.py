"""
API для работы с типами entities.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.crm.color_palette import assign_color_from_palette
from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.dependencies import ContainerDep
from apps.crm.entity_type_list_filter import resolve_list_entity_query_pair
from apps.crm.models.api import EntityTypeCreate, EntityTypeResponse, EntityTypeUpdate
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/entity-types", tags=["EntityTypes"])


class UpdatePublicFieldsRequest(BaseModel):
    """Запрос на обновление публичных полей"""

    public_fields: list[str]


async def _parent_maps_for_types(
    repo: EntityTypeRepository,
    types: list[EntityType],
) -> dict[str, dict[str, str | None]]:
    namespaces = {t.namespace for t in types if t.namespace.strip()}
    out: dict[str, dict[str, str | None]] = {}
    for ns in sorted(namespaces):
        out[ns] = await repo.get_parent_type_id_map_for_namespace(ns)
    return out


async def _backfill_missing_colors(
    types: list[EntityType],
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
        await repo.update_color(
            entity_type.type_id,
            entity_type.namespace,
            assigned_color,
        )
        updated = True
    return updated


async def _list_entity_types_offset_page(
    repo: EntityTypeRepository,
    *,
    namespace: str | None,
    limit: int,
    offset: int,
) -> OffsetPage[EntityTypeResponse]:
    types, total = await asyncio.gather(
        repo.get_all_for_company(namespace=namespace, limit=limit, offset=offset),
        repo.count_all_for_company(namespace=namespace),
    )
    if not types:
        return OffsetPage[EntityTypeResponse](
            items=[],
            total=total,
            limit=limit,
            offset=offset,
        )
    parent_maps = await _parent_maps_for_types(repo, types)
    if await _backfill_missing_colors(types, repo):
        types = await repo.get_all_for_company(
            namespace=namespace,
            limit=limit,
            offset=offset,
        )
        parent_maps = await _parent_maps_for_types(repo, types)
    items = [_entity_type_to_response(t, parent_maps[t.namespace]) for t in types]
    return OffsetPage[EntityTypeResponse](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


def _entity_type_to_response(
    entity: EntityType,
    parent_map: dict[str, str | None],
) -> EntityTypeResponse:
    lt, ls = resolve_list_entity_query_pair(entity.type_id, parent_map)
    return EntityTypeResponse(
        type_id=entity.type_id,
        company_id=entity.company_id,
        namespace=entity.namespace,
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
        is_context_anchor=entity.is_context_anchor,
        is_voice_target=entity.is_voice_target,
        auto_resolve_suggests=entity.auto_resolve_suggests,
        extractable=entity.extractable,
        created_at=entity.created_at,
        list_entity_type=lt,
        list_entity_subtype=ls,
    )


@router.get("", response_model=OffsetPage[EntityTypeResponse])
async def list_entity_types(
    container: ContainerDep,
    namespace: Annotated[str | None, Query(description="Фильтр по пространству")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[EntityTypeResponse]:
    return await _list_entity_types_offset_page(
        container.entity_type_repository,
        namespace=namespace,
        limit=limit,
        offset=offset,
    )


@router.get("/by-namespace/{namespace}", response_model=OffsetPage[EntityTypeResponse])
async def list_entity_types_by_namespace(
    namespace: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[EntityTypeResponse]:
    normalized_namespace = namespace.strip()
    if not normalized_namespace:
        raise HTTPException(status_code=422, detail="namespace is required")
    return await _list_entity_types_offset_page(
        container.entity_type_repository,
        namespace=normalized_namespace,
        limit=limit,
        offset=offset,
    )


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    container: ContainerDep,
    namespace: Annotated[str, Query(description="Пространство строки типа")],
):
    repo = container.entity_type_repository
    ns = namespace.strip()
    if not ns:
        raise HTTPException(status_code=422, detail="namespace is required")
    entity_type = await repo.get_by_type_id(type_id, namespace=ns)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    if not entity_type.color or not entity_type.color.strip():
        assigned_color = assign_color_from_palette(set())
        await repo.update_color(type_id, ns, assigned_color)
        entity_type.color = assigned_color
    parent_map = await repo.get_parent_type_id_map_for_namespace(ns)
    return _entity_type_to_response(entity_type, parent_map)


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    data: EntityTypeCreate,
    container: ContainerDep,
):
    repo = container.entity_type_repository
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    company_id = context.active_company.company_id
    ns = data.namespace.strip()
    if not ns:
        raise HTTPException(status_code=422, detail="namespace is required")

    dup = await repo.get_by_type_id(data.type_id, namespace=ns, company_id=company_id)
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail=f"EntityType {data.type_id!r} already exists in namespace {ns!r}",
        )

    existing_types = await repo.load_all_entity_types_for_company()
    used_colors = {
        et.color for et in existing_types if isinstance(et.color, str) and et.color.strip()
    }
    resolved_color = data.color
    if not resolved_color or not resolved_color.strip():
        resolved_color = assign_color_from_palette(used_colors)

    entity_type = EntityType(
        type_id=data.type_id,
        namespace=ns,
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
        company_id=company_id,
        is_context_anchor=data.is_context_anchor,
        is_voice_target=data.is_voice_target,
        auto_resolve_suggests=data.auto_resolve_suggests,
    )

    _ = await repo.create_custom_type(entity_type, company_id)
    parent_map = await repo.get_parent_type_id_map_for_namespace(ns)
    refreshed = await repo.get_by_type_id(data.type_id, namespace=ns)
    if not refreshed:
        raise HTTPException(status_code=500, detail="EntityType not found after create")
    return _entity_type_to_response(refreshed, parent_map)


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    data: EntityTypeUpdate,
    container: ContainerDep,
    namespace: Annotated[str, Query(description="Пространство строки типа")],
):
    repo = container.entity_type_repository
    ns = namespace.strip()
    if not ns:
        raise HTTPException(status_code=422, detail="namespace is required")
    entity_type = await repo.get_by_type_id(type_id, namespace=ns)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")

    fields: dict[str, object] = {}
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
    if data.auto_resolve_suggests is not None:
        fields["auto_resolve_suggests"] = data.auto_resolve_suggests

    raw_color = fields.get("color")
    resolved_color = raw_color if isinstance(raw_color, str) else entity_type.color
    if not resolved_color or not resolved_color.strip():
        fields["color"] = assign_color_from_palette(set())

    if fields:
        await repo.update_metadata_fields(type_id, namespace=ns, fields=fields)

    entity_type = await repo.get_by_type_id(type_id, namespace=ns)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    parent_map = await repo.get_parent_type_id_map_for_namespace(ns)
    return _entity_type_to_response(entity_type, parent_map)


@router.put("/{type_id}/public-fields", response_model=EntityTypeResponse)
async def update_public_fields(
    type_id: str,
    data: UpdatePublicFieldsRequest,
    container: ContainerDep,
    namespace: Annotated[str, Query(description="Пространство строки типа")],
):
    repo = container.entity_type_repository
    ns = namespace.strip()
    if not ns:
        raise HTTPException(status_code=422, detail="namespace is required")
    entity_type = await repo.get_by_type_id(type_id, namespace=ns)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")

    await repo.update_metadata(type_id, namespace=ns, public_fields=data.public_fields)

    entity_type = await repo.get_by_type_id(type_id, namespace=ns)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    parent_map = await repo.get_parent_type_id_map_for_namespace(ns)
    return _entity_type_to_response(entity_type, parent_map)
