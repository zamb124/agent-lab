"""
API для работы со связями (relationships).
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from apps.crm.db.models import Relationship, RelationshipType
from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    RelationshipCreate,
    RelationshipResponse,
    RelationshipTypeCreate,
    RelationshipTypeResponse,
)
from apps.crm.models.graph import ShortestPathResponse
from apps.crm.services.graph_service import GraphEntityLimitExceededError
from core.context import get_context
from core.logging import get_logger
from core.pagination import CursorPage, OffsetPage

logger = get_logger(__name__)

router = APIRouter(prefix="/relationships", tags=["Relationships"])


@router.get("", response_model=CursorPage[RelationshipResponse])
async def list_relationships(
    container: ContainerDep,
    entity_id: Optional[str] = Query(None, description="Фильтр по entity (source или target)"),
    namespace: Optional[str] = Query(None, description="Фильтр по namespace"),
    cursor: Optional[str] = Query(None, description="Cursor для следующей страницы"),
    limit: int = Query(200, ge=1, le=1000, description="Размер страницы"),
):
    """Связи с cursor-пагинацией. Без entity_id возвращает все связи компании постранично."""
    repo = container.relationship_repository

    if namespace is not None and namespace.strip() == "":
        raise HTTPException(status_code=400, detail="namespace must not be empty")

    if entity_id:
        relationships = await repo.get_by_entity(entity_id)
        if namespace is not None:
            relationships = [r for r in relationships if r.namespace == namespace]
        return CursorPage[RelationshipResponse](
            items=relationships,
            next_cursor=None,
            has_more=False,
        )

    batch, next_cursor, has_more = await repo.get_all_for_graph(limit=limit, cursor=cursor)
    if namespace is not None:
        batch = [r for r in batch if r.namespace == namespace]
    return CursorPage[RelationshipResponse](
        items=batch,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{relationship_id}", response_model=RelationshipResponse)
async def get_relationship(
    relationship_id: str,
    container: ContainerDep,
):
    """Получить связь по ID"""
    relationship = await container.relationship_repository.get(relationship_id)
    if not relationship:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return relationship


@router.post("", response_model=RelationshipResponse)
async def create_relationship(
    data: RelationshipCreate,
    container: ContainerDep,
):
    """Создать новую связь"""

    context = get_context()
    company_id = context.active_company.company_id

    all_types = await container.relationship_type_repository.get_all_for_company(include_system=True)
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
        confidence=data.confidence,
        attributes=data.attributes or {},
        company_id=company_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    try:
        await container.relationship_repository.create(relationship)
    except IntegrityError as exc:
        if "uq_relationships_unique_edge" in str(exc):
            raise HTTPException(status_code=409, detail="Relationship already exists")
        raise
    return relationship


@router.delete("/{relationship_id}")
async def delete_relationship(
    relationship_id: str,
    container: ContainerDep,
):
    """Удалить связь"""
    success = await container.relationship_repository.delete(relationship_id)
    if not success:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return {"status": "deleted"}


@router.get("/types/", response_model=OffsetPage[RelationshipTypeResponse])
async def list_relationship_types(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[RelationshipTypeResponse]:
    repo = container.relationship_type_repository
    types, total = await asyncio.gather(
        repo.get_all_for_company(include_system=True, limit=limit, offset=offset),
        repo.count_all_for_company(include_system=True),
    )
    return OffsetPage[RelationshipTypeResponse](items=types, total=total, limit=limit, offset=offset)


@router.post("/types/", response_model=RelationshipTypeResponse)
async def create_relationship_type(
    data: RelationshipTypeCreate,
    container: ContainerDep,
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

    await container.relationship_type_repository.create_custom_type(rel_type)
    return rel_type


@router.get("/path/", response_model=ShortestPathResponse)
async def find_shortest_path(
    container: ContainerDep,
    from_entity_id: str = Query(..., alias="from", description="ID начальной entity"),
    to_entity_id: str = Query(..., alias="to", description="ID конечной entity"),
    max_depth: int = Query(10, ge=1, le=20, description="Максимальная глубина поиска"),
    created_at_from: Optional[datetime] = Query(None, description="Фильтр created_at >= value"),
    created_at_to: Optional[datetime] = Query(None, description="Фильтр created_at <= value"),
    namespace: Optional[str] = Query(
        None,
        description=(
            "Namespace пространства данных. При непустом значении используется и для "
            "лимита сущностей, и как фильтр Relationship.namespace при обходе."
        ),
    ),
    include_all_namespaces: bool = Query(
        False,
        description=(
            "Если true и задан namespace — обход берёт связи всех Relationship.namespace."
        ),
    ),
):
    """
    Кратчайший путь между entities с учетом весов.

    Использует:
    - Алгоритм: Bidirectional Weighted Dijkstra
    - Учитывает weight из Relationship
    - Возвращает два расчета: directed и undirected

    При непустом ``namespace`` обход видит только связи с тем же
    ``Relationship.namespace`` (если не передан ``include_all_namespaces``).

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
        path = await container.graph_service.find_shortest_path(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            max_depth=max_depth,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            namespace=namespace,
            include_all_namespaces=include_all_namespaces,
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
