"""
API для типов сущностей CRM.
"""

from typing import List

from fastapi import APIRouter, HTTPException

from apps.crm.dependencies import EntityTypeServiceDep
from apps.crm.models.entity_type_models import (
    EntityTypeCreate,
    EntityTypeUpdate,
    EntityTypeResponse,
)

router = APIRouter()


@router.get("", response_model=List[EntityTypeResponse])
async def list_entity_types(
    entity_type_service: EntityTypeServiceDep,
):
    """Получает все типы сущностей (системные + кастомные)"""
    return await entity_type_service.get_all_types()


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    entity_type_service: EntityTypeServiceDep,
):
    """Получает тип по ID"""
    entity_type = await entity_type_service.get_type(type_id)
    if not entity_type:
        raise HTTPException(status_code=404, detail="Тип не найден")
    return entity_type


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    data: EntityTypeCreate,
    entity_type_service: EntityTypeServiceDep,
):
    """Создает кастомный тип сущности"""
    return await entity_type_service.create_type(data)


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    data: EntityTypeUpdate,
    entity_type_service: EntityTypeServiceDep,
):
    """Обновляет тип сущности (только кастомные)"""
    entity_type = await entity_type_service.update_type(type_id, data)
    if not entity_type:
        raise HTTPException(status_code=404, detail="Тип не найден")
    return entity_type


@router.delete("/{type_id}")
async def delete_entity_type(
    type_id: str,
    entity_type_service: EntityTypeServiceDep,
):
    """Удаляет кастомный тип сущности"""
    success = await entity_type_service.delete_type(type_id)
    if not success:
        raise HTTPException(status_code=404, detail="Тип не найден")
    return {"status": "deleted"}


