"""
API для работы со связями (relationships).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    RelationshipCreate,
    RelationshipResponse,
    RelationshipTypeCreate,
    RelationshipTypeResponse,
)
from apps.crm.models.graph import ShortestPathResponse
from apps.crm.realtime.operations import (
    CrmOffsetPagePayload,
    CrmRelationshipIdPayload,
    CrmRelationshipsListPayload,
    CrmRelationshipsPathPayload,
    op_relationship_types_create,
    op_relationship_types_list,
    op_relationships_create,
    op_relationships_item,
    op_relationships_list,
    op_relationships_path,
    op_relationships_remove,
)
from core.context import require_context
from core.pagination import CursorPage, OffsetPage

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
) -> CursorPage[RelationshipResponse]:
    return await op_relationships_list(
        CrmRelationshipsListPayload(
            entity_id=entity_id,
            namespace=namespace,
            cursor=cursor,
            limit=limit,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/{relationship_id}", response_model=RelationshipResponse)
async def get_relationship(
    relationship_id: str,
    container: ContainerDep,
):
    return await op_relationships_item(
        CrmRelationshipIdPayload(relationship_id=relationship_id),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=RelationshipResponse)
async def create_relationship(
    data: RelationshipCreate,
    container: ContainerDep,
):
    return await op_relationships_create(
        data, user=require_context().user, container=container
    )


@router.delete("/{relationship_id}", status_code=204)
async def delete_relationship(
    relationship_id: str,
    container: ContainerDep,
) -> Response:
    await op_relationships_remove(
        CrmRelationshipIdPayload(relationship_id=relationship_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.get("/types/", response_model=OffsetPage[RelationshipTypeResponse])
async def list_relationship_types(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[RelationshipTypeResponse]:
    return await op_relationship_types_list(
        CrmOffsetPagePayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("/types/", response_model=RelationshipTypeResponse)
async def create_relationship_type(
    data: RelationshipTypeCreate,
    container: ContainerDep,
):
    return await op_relationship_types_create(
        data, user=require_context().user, container=container
    )


@router.get("/path/", response_model=ShortestPathResponse)
async def find_shortest_path(
    container: ContainerDep,
    source_entity_id: Annotated[str, Query(description="ID начальной сущности")],
    target_entity_id: Annotated[str, Query(description="ID конечной сущности")],
    max_depth: Annotated[int, Query(ge=1, le=20)] = 10,
    created_at_from: Annotated[datetime | None, Query()] = None,
    created_at_to: Annotated[datetime | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    include_all_namespaces: Annotated[bool, Query()] = False,
):
    return await op_relationships_path(
        CrmRelationshipsPathPayload(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            max_depth=max_depth,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            namespace=namespace,
            include_all_namespaces=include_all_namespaces,
        ),
        user=require_context().user,
        container=container,
    )
