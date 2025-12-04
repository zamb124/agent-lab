"""
API для связей между сущностями CRM.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import RelationshipServiceDep
from apps.crm.models.relationship_models import RelationshipCreate, RelationshipResponse

router = APIRouter()


@router.get("", response_model=List[RelationshipResponse])
async def list_relationships(
    relationship_service: RelationshipServiceDep,
    relationship_type: Optional[str] = Query(None, description="Фильтр по типу"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Получает список связей"""
    return await relationship_service.list_relationships(
        relationship_type=relationship_type,
        limit=limit,
        offset=offset,
    )


@router.get("/entity/{entity_id}", response_model=List[RelationshipResponse])
async def get_entity_relationships(
    entity_id: str,
    relationship_service: RelationshipServiceDep,
    include_entities: bool = Query(False, description="Включить данные связанных сущностей"),
):
    """Получает все связи сущности"""
    return await relationship_service.get_entity_relationships(
        entity_id, include_entities=include_entities
    )


@router.get("/{relationship_id}", response_model=RelationshipResponse)
async def get_relationship(
    relationship_id: str,
    relationship_service: RelationshipServiceDep,
):
    """Получает связь по ID"""
    relationship = await relationship_service.get_relationship(relationship_id)
    if not relationship:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    return relationship


@router.post("", response_model=RelationshipResponse)
async def create_relationship(
    data: RelationshipCreate,
    relationship_service: RelationshipServiceDep,
):
    """Создает связь между сущностями"""
    try:
        return await relationship_service.create_relationship(data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{relationship_id}")
async def delete_relationship(
    relationship_id: str,
    relationship_service: RelationshipServiceDep,
):
    """Удаляет связь"""
    success = await relationship_service.delete_relationship(relationship_id)
    if not success:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    return {"status": "deleted"}


@router.get("/between/{entity_id_1}/{entity_id_2}", response_model=List[RelationshipResponse])
async def get_relationships_between(
    entity_id_1: str,
    entity_id_2: str,
    relationship_service: RelationshipServiceDep,
):
    """Получает связи между двумя сущностями"""
    return await relationship_service.get_relationships_between(entity_id_1, entity_id_2)

