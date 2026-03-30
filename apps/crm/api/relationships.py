"""
API для работы со связями (relationships).
"""

import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query

from apps.crm.models.api import RelationshipCreate, RelationshipResponse, RelationshipTypeCreate, RelationshipTypeResponse
from apps.crm.models.graph import ShortestPathResponse
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.services.graph_service import GraphEntityLimitExceededError, GraphService
from apps.crm.container import get_crm_container
from apps.crm.dependencies import get_graph_service
from apps.crm.db.models import Relationship, RelationshipType
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/relationships", tags=["Relationships"])


def get_relationship_repo() -> RelationshipRepository:
    """Получить репозиторий связей"""
    container = get_crm_container()
    return container.relationship_repository


def get_relationship_type_repo() -> RelationshipTypeRepository:
    """Получить репозиторий типов связей"""
    container = get_crm_container()
    return container.relationship_type_repository


@router.get("", response_model=List[RelationshipResponse])
async def list_relationships(
    entity_id: str = None,
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    limit: int = Query(1000, ge=1, le=10000, description="Лимит для полного списка связей"),
    repo: RelationshipRepository = Depends(get_relationship_repo)
):
    """Получить все связи (опционально для конкретной entity)"""
    if entity_id:
        relationships = await repo.get_by_entity(entity_id)
    else:
        relationships = await repo.get_all_for_graph(limit=limit)
    if namespace is None:
        return relationships
    if namespace.strip() == "":
        raise HTTPException(status_code=400, detail="namespace must not be empty")
    return [rel for rel in relationships if rel.namespace == namespace]


@router.get("/{relationship_id}", response_model=RelationshipResponse)
async def get_relationship(
    relationship_id: str,
    repo: RelationshipRepository = Depends(get_relationship_repo)
):
    """Получить связь по ID"""
    relationship = await repo.get(relationship_id)
    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return relationship


@router.post("", response_model=RelationshipResponse)
async def create_relationship(
    data: RelationshipCreate,
    repo: RelationshipRepository = Depends(get_relationship_repo),
    type_repo: RelationshipTypeRepository = Depends(get_relationship_type_repo),
):
    """Создать новую связь"""

    context = get_context()
    company_id = context.active_company.company_id

    all_types = await type_repo.get_all_for_company(include_system=True)
    valid_type_ids = {t.type_id for t in all_types}
    if data.relationship_type not in valid_type_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown relationship_type: {data.relationship_type}",
        )

    relationship = Relationship(
        relationship_id=str(uuid.uuid4()),
        source_entity_id=data.source_entity_id,
        target_entity_id=data.target_entity_id,
        relationship_type=data.relationship_type,
        namespace=data.namespace,
        weight=data.weight,
        attributes=data.attributes or {},
        company_id=company_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    await repo.create(relationship)
    return relationship


@router.delete("/{relationship_id}")
async def delete_relationship(
    relationship_id: str,
    repo: RelationshipRepository = Depends(get_relationship_repo)
):
    """Удалить связь"""
    success = await repo.delete(relationship_id)
    if not success:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return {"status": "deleted"}


@router.get("/types/", response_model=List[RelationshipTypeResponse])
async def list_relationship_types(
    repo: RelationshipTypeRepository = Depends(get_relationship_type_repo)
):
    """Получить все типы связей для компании"""
    types = await repo.get_all_for_company(include_system=True)
    return types


@router.post("/types/", response_model=RelationshipTypeResponse)
async def create_relationship_type(
    data: RelationshipTypeCreate,
    repo: RelationshipTypeRepository = Depends(get_relationship_type_repo)
):
    """Создать кастомный тип связи (скрыт из UI, доступен по API)"""

    rel_type = RelationshipType(
        type_id=data.type_id,
        name=data.name,
        description=data.description,
        prompt=data.prompt,
        is_directed=data.is_directed,
        inverse_type_id=data.inverse_type_id,
        icon=data.icon,
        color=data.color,
        weight_default=data.weight_default,
        is_system=False,
    )

    await repo.create_custom_type(rel_type)
    return rel_type


@router.get("/path/", response_model=ShortestPathResponse)
async def find_shortest_path(
    from_entity_id: str = Query(..., alias="from", description="ID начальной entity"),
    to_entity_id: str = Query(..., alias="to", description="ID конечной entity"),
    max_depth: int = Query(10, ge=1, le=20, description="Максимальная глубина поиска"),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    namespace: Optional[str] = Query(None, description="Namespace для проверки лимита сущностей в БД"),
    service: GraphService = Depends(get_graph_service)
):
    """
    Кратчайший путь между entities с учетом весов.
    
    Использует:
    - Алгоритм: Bidirectional Weighted Dijkstra
    - Учитывает weight из Relationship
    - Возвращает два расчета: directed и undirected
    
    Args:
        from_entity_id: Начальная entity
        to_entity_id: Конечная entity
        max_depth: Максимальная глубина поиска (1-20)
    
    Returns:
        Кратчайший путь с edges и total_distance
    
    Raises:
        404: Entity не найдена
        403: Нет доступа к entity
    """
    try:
        path = await service.find_shortest_path(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            max_depth=max_depth,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            namespace=namespace,
        )
        return path
    except GraphEntityLimitExceededError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error finding shortest path: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

