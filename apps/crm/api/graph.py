"""REST-зеркало графа связей: те же `op_*`, что и WS RPC."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.graph import InfluenceGraphResponse, RelatedEntitiesResponse
from apps.crm.realtime.operations import (
    CrmEntitiesInfluenceGraphPayload,
    CrmEntitiesRelatedPayload,
    CrmOverviewGraphPayload,
    op_entities_influence_graph,
    op_entities_overview_graph,
    op_entities_related,
)
from core.context import require_context

router = APIRouter(prefix="/entities", tags=["Graph"])


@router.post("/overview-graph", response_model=InfluenceGraphResponse)
async def get_overview_graph(
    payload: CrmOverviewGraphPayload,
    container: ContainerDep,
) -> InfluenceGraphResponse:
    return await op_entities_overview_graph(
        payload, user=require_context().user, container=container
    )


@router.get("/{entity_id}/influence-graph", response_model=InfluenceGraphResponse)
async def get_influence_graph(
    entity_id: str,
    container: ContainerDep,
    max_depth: Annotated[int, Query(ge=1, le=5)] = 3,
    relationship_types: Annotated[list[str] | None, Query()] = None,
    created_at_from: Annotated[datetime | None, Query()] = None,
    created_at_to: Annotated[datetime | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    include_all_namespaces: Annotated[bool, Query()] = False,
) -> InfluenceGraphResponse:
    return await op_entities_influence_graph(
        CrmEntitiesInfluenceGraphPayload(
            entity_id=entity_id,
            max_depth=max_depth,
            relationship_types=relationship_types,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            namespace=namespace,
            include_all_namespaces=include_all_namespaces,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/{entity_id}/related", response_model=RelatedEntitiesResponse)
async def get_related_entities(
    entity_id: str,
    container: ContainerDep,
    direction: Annotated[Literal["incoming", "outgoing", "both"], Query()] = "both",
    relationship_type: Annotated[str | None, Query()] = None,
    created_at_from: Annotated[datetime | None, Query()] = None,
    created_at_to: Annotated[datetime | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    include_all_namespaces: Annotated[bool, Query()] = False,
) -> RelatedEntitiesResponse:
    return await op_entities_related(
        CrmEntitiesRelatedPayload(
            entity_id=entity_id,
            direction=direction,
            relationship_type=relationship_type,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            namespace=namespace,
            include_all_namespaces=include_all_namespaces,
        ),
        user=require_context().user,
        container=container,
    )
