"""
API для работы со связями (relationships).
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

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
    entity_id: Annotated[
        str | None, Query(description="Фильтр по entity (source или target)")
    ] = None,
    namespace: Annotated[str | None, Query(description="Фильтр по namespace")] = None,
    cursor: Annotated[str | None, Query(description="Cursor для следующей страницы")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Размер страницы")] = 200,
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
            items=[RelationshipResponse.model_validate(row) for row in relationships],
            next_cursor=None,
            has_more=False,
        )

    batch, next_cursor, has_more = await repo.get_all_for_graph(limit=limit, cursor=cursor)
    if namespace is not None:
        batch = [r for r in batch if r.namespace == namespace]
    return CursorPage[RelationshipResponse](
        items=[RelationshipResponse.model_validate(row) for row in batch],
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
    if context is None or context.active_company is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    company_id = context.active_company.company_id

    all_types = await container.relationship_type_repository.list_by_company(
        include_system=True
    )
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    try:
        _ = await container.relationship_repository.create(relationship)
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
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[RelationshipTypeResponse]:
    repo = container.relationship_type_repository
    types, total = await asyncio.gather(
        repo.list_by_company(include_system=True, limit=limit, offset=offset),
        repo.count_all_for_company(include_system=True),
    )
    return OffsetPage[RelationshipTypeResponse](
        items=[RelationshipTypeResponse.model_validate(row) for row in types],
        total=total,
        limit=limit,
        offset=offset,
    )


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

    _ = await container.relationship_type_repository.create_custom_type(rel_type)
    return rel_type


@router.get("/path/", response_model=ShortestPathResponse)
async def find_shortest_path(
    container: ContainerDep,
    from_entity_id: Annotated[str, Query(alias="from", description="ID начальной entity")],
    to_entity_id: Annotated[str, Query(alias="to", description="ID конечной entity")],
    max_depth: Annotated[int, Query(ge=1, le=20, description="Максимальная глубина поиска")] = 10,
    created_at_from: Annotated[
        datetime | None, Query(description="Фильтр created_at >= value")
    ] = None,
    created_at_to: Annotated[
        datetime | None, Query(description="Фильтр created_at <= value")
    ] = None,
    namespace: Annotated[
        str | None,
        Query(
            description=(
                "Namespace пространства данных. При непустом значении используется и для "
                "лимита сущностей, и как фильтр Relationship.namespace при обходе."
            ),
        ),
    ] = None,
    include_all_namespaces: Annotated[
        bool,
        Query(
            description=(
                "Если true и задан namespace — обход берёт связи всех Relationship.namespace."
            ),
        ),
    ] = False,
):
    """
    Кратчайший путь между entities с учетом весов.

    Использует:
    - Алгоритм: двунаправленный взвешенный Dijkstra
    - Учитывает weight из Relationship
    - Возвращает два расчета: directed и undirected

    При непустом ``namespace`` обход видит только связи с тем же
    ``Relationship.namespace`` (если не передан ``include_all_namespaces``).

    Аргументы:
        from_entity_id: Начальная entity
        to_entity_id: Конечная entity
        max_depth: Максимальная глубина поиска (1-20)

    Возвращает:
        Кратчайший путь с edges и total_distance

    Исключения:
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
