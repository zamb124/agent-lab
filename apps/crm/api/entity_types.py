"""
API для работы с типами entities.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.crm.models.api import EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.container import get_crm_container
from apps.crm.db.models import EntityType

router = APIRouter(prefix="/entity-types", tags=["EntityTypes"])


class UpdatePublicFieldsRequest(BaseModel):
    """Запрос на обновление публичных полей"""
    public_fields: List[str]


def get_entity_type_repo() -> EntityTypeRepository:
    """Получить репозиторий типов entities"""
    container = get_crm_container()
    return container.entity_type_repository


@router.get("", response_model=List[EntityTypeResponse])
async def list_entity_types(
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Получить все типы entities для компании"""
    from core.context import get_context
    
    context = get_context()
    company_id = context.active_company.company_id
    
    types = await repo.get_all_for_company(company_id)
    return types


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Получить тип entity по ID"""
    entity_type = await repo.get(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    return entity_type


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    data: EntityTypeCreate,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Создать новый тип entity"""
    
    
    entity_type = EntityType(
        type_id=data.type_id,
        name=data.name,
        description=data.description,
        parent_type_id=data.parent_type_id,
        prompt=data.prompt,
        required_fields=data.required_fields or {},
        optional_fields=data.optional_fields or {},
        icon=data.icon,
        color=data.color,
        is_system=False,
        is_event=data.is_event,
        check_duplicates=data.check_duplicates,
        company_id="system"
    )
    
    await repo.create(entity_type)
    return entity_type


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    data: EntityTypeUpdate,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Обновить тип entity"""
    entity_type = await repo.get(type_id)
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
    
    await repo.update(entity_type)
    return entity_type


@router.put("/{type_id}/public-fields", response_model=EntityTypeResponse)
async def update_public_fields(
    type_id: str,
    data: UpdatePublicFieldsRequest,
    repo: EntityTypeRepository = Depends(get_entity_type_repo)
):
    """Обновить список публичных полей для типа"""
    from core.context import get_context
    
    context = get_context()
    company_id = context.active_company.company_id
    
    entity_type = await repo.get(type_id, company_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="EntityType not found")
    
    entity_type.public_fields = data.public_fields
    await repo.update(entity_type)
    
    return entity_type

