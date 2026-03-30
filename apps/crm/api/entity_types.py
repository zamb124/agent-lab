"""
API для работы с типами entities.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from apps.crm.models.api import EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.container import get_crm_container
from apps.crm.db.models import EntityType
from apps.crm.color_palette import ENTITY_COLOR_PALETTE, assign_color_from_palette
from core.context import get_context

router = APIRouter(prefix="/entity-types", tags=["EntityTypes"])


class UpdatePublicFieldsRequest(BaseModel):
    """Запрос на обновление публичных полей"""
    public_fields: List[str]


def get_entity_type_repo() -> EntityTypeRepository:
    """Получить репозиторий типов entities"""
    container = get_crm_container()
    return container.entity_type_repository


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
        entity_type.color = assigned_color
        used_colors.add(assigned_color)
        await repo.update(entity_type)
        updated = True
    return updated


@router.get("", response_model=List[EntityTypeResponse])
async def list_entity_types(
    namespace: Optional[str] = Query(default=None, description="Фильтр разрешенных типов по namespace"),
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Получить все типы entities для компании"""
    types = await repo.get_all_for_company(namespace=namespace)
    if await _backfill_missing_colors(types, repo):
        types = await repo.get_all_for_company(namespace=namespace)
    return types


@router.get("/by-namespace/{namespace}", response_model=List[EntityTypeResponse])
async def list_entity_types_by_namespace(
    namespace: str,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Получить типы сущностей, разрешенные в namespace."""
    normalized_namespace = namespace.strip()
    if not normalized_namespace:
        raise HTTPException(status_code=422, detail="namespace is required")
    types = await repo.list_allowed_for_namespace(normalized_namespace)
    if await _backfill_missing_colors(types, repo):
        return await repo.list_allowed_for_namespace(normalized_namespace)
    return types


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Получить тип entity по ID"""
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    if not entity_type.color or not entity_type.color.strip():
        entity_type.color = assign_color_from_palette(set())
        await repo.update(entity_type)
    return entity_type


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    data: EntityTypeCreate,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Создать новый тип entity"""
    context = get_context()
    company_id = context.active_company.company_id
    namespace_ids = data.namespace_ids or ["default"]
    if len(namespace_ids) == 0:
        raise HTTPException(status_code=422, detail="namespace_ids must not be empty")

    existing_types = await repo.get_all_for_company()
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
        company_id=company_id
    )
    
    await repo.create_custom_type(entity_type, company_id)
    return entity_type


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    data: EntityTypeUpdate,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Обновить тип entity"""
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    
    if data.name is not None:
        entity_type.name = data.name
    if data.description is not None:
        entity_type.description = data.description
    if data.parent_type_id is not None:
        entity_type.parent_type_id = data.parent_type_id
    if data.prompt is not None:
        entity_type.prompt = data.prompt
    if data.required_fields is not None:
        entity_type.required_fields = data.required_fields
    if data.optional_fields is not None:
        entity_type.optional_fields = data.optional_fields
    if data.icon is not None:
        entity_type.icon = data.icon
    if data.color is not None:
        entity_type.color = data.color
    if data.namespace_ids is not None:
        if len(data.namespace_ids) == 0:
            raise HTTPException(status_code=422, detail="namespace_ids must not be empty")
        entity_type.namespace_ids = data.namespace_ids
    if not entity_type.color or not entity_type.color.strip():
        entity_type.color = assign_color_from_palette(set())
    
    await repo.update(entity_type)
    return entity_type


@router.put("/{type_id}/public-fields", response_model=EntityTypeResponse)
async def update_public_fields(
    type_id: str,
    data: UpdatePublicFieldsRequest,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Обновить список публичных полей для типа"""
    entity_type = await repo.get_by_type_id(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    
    entity_type.public_fields = data.public_fields
    await repo.update(entity_type)
    
    return entity_type
