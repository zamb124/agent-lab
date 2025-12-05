"""
API для сущностей CRM.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import EntityServiceDep
from apps.crm.models.entity_models import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntitySearchRequest,
    EntitySearchResponse,
    EntityStatus,
)

router = APIRouter()


@router.get("", response_model=List[EntityResponse])
async def list_entities(
    entity_service: EntityServiceDep,
    entity_type: Optional[str] = Query(None, description="Фильтр по типу"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Получает список сущностей"""
    return await entity_service.list_entities(entity_type=entity_type, limit=limit)


@router.get("/autocomplete", response_model=List[EntityResponse])
async def autocomplete_entities(
    entity_service: EntityServiceDep,
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    entity_type: Optional[str] = Query(None, description="Фильтр по типу"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Быстрый поиск сущностей для @mention autocomplete.
    Ищет по имени с использованием семантического поиска.
    """
    from apps.crm.models.entity_models import EntitySearchRequest
    
    request = EntitySearchRequest(
        query=q,
        entity_type=entity_type,
        limit=limit
    )
    result = await entity_service.search_entities(request)
    return result.entities


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: str,
    entity_service: EntityServiceDep,
):
    """Получает сущность по ID"""
    entity = await entity_service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Сущность не найдена")
    return entity


@router.post("", response_model=EntityResponse)
async def create_entity(
    data: EntityCreate,
    entity_service: EntityServiceDep,
):
    """Создает новую сущность"""
    return await entity_service.create_entity(data)


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    entity_service: EntityServiceDep,
):
    """Обновляет сущность"""
    entity = await entity_service.update_entity(entity_id, data)
    if not entity:
        raise HTTPException(status_code=404, detail="Сущность не найдена")
    return entity


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    entity_service: EntityServiceDep,
):
    """Удаляет сущность"""
    success = await entity_service.delete_entity(entity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Сущность не найдена")
    return {"status": "deleted"}


@router.put("/{entity_id}/status", response_model=EntityResponse)
async def update_entity_status(
    entity_id: str,
    status: EntityStatus,
    entity_service: EntityServiceDep,
):
    """Обновляет статус сущности (pending -> approved/rejected)"""
    entity = await entity_service.update_entity_status(entity_id, status)
    if not entity:
        raise HTTPException(status_code=404, detail="Сущность не найдена")
    return entity


@router.post("/search", response_model=EntitySearchResponse)
async def search_entities(
    request: EntitySearchRequest,
    entity_service: EntityServiceDep,
):
    """Семантический поиск по сущностям"""
    return await entity_service.search_entities(request)


@router.post("/find-duplicates", response_model=List[EntityResponse])
async def find_duplicates(
    data: EntityCreate,
    entity_service: EntityServiceDep,
    threshold: float = Query(0.85, ge=0.0, le=1.0),
):
    """Находит потенциальные дубликаты для сущности"""
    return await entity_service.find_duplicates(data, threshold)


