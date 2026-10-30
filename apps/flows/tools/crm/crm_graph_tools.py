"""CRM graph tools — thin wrappers over CrmClient."""

from __future__ import annotations

from typing import Literal

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.clients.crm_client import CrmClient
from core.clients.crm_models import (
    CrmDeleteRelationshipArgs,
    CrmEntityRelatedArgs,
    CrmListRelationshipsArgs,
    CrmListRelationshipTypesArgs,
    CrmShortestPathArgs,
)
from core.types import JsonObject

_TAGS = ["crm"]


@tool(
    name="crm_list_relationships",
    description=(
        "Lists CRM relationships (GET /crm/api/v1/relationships). "
        "Prefer entity_id to list edges for one node. Returns items with relationship_id."
    ),
    tags=_TAGS,
    parameters_model=CrmListRelationshipsArgs,
)
async def crm_list_relationships(
    entity_id: str | None = None,
    namespace: str | None = None,
    limit: int = 200,
    cursor: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_relationships(
        entity_id=entity_id,
        namespace=namespace,
        limit=limit,
        cursor=cursor,
    )


@tool(
    name="crm_delete_relationship",
    description=(
        "Deletes a CRM relationship by relationship_id "
        "(DELETE /crm/api/v1/relationships/{relationship_id}). Confirm with the user first."
    ),
    tags=_TAGS,
    parameters_model=CrmDeleteRelationshipArgs,
)
async def crm_delete_relationship(relationship_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await CrmClient().delete_relationship(relationship_id)


@tool(
    name="crm_list_relationship_types",
    description=(
        "Lists relationship type catalog "
        "(GET /crm/api/v1/relationships/types/). Use type_id as relationship_type when creating edges."
    ),
    tags=_TAGS,
    parameters_model=CrmListRelationshipTypesArgs,
)
async def crm_list_relationship_types(
    limit: int = 200,
    offset: int = 0,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_relationship_types(limit=limit, offset=offset)


@tool(
    name="crm_entity_related",
    description=(
        "One-hop related entities "
        "(GET /crm/api/v1/entities/{entity_id}/related). Returns incoming/outgoing/undirected."
    ),
    tags=_TAGS,
    parameters_model=CrmEntityRelatedArgs,
)
async def crm_entity_related(
    entity_id: str,
    direction: Literal["incoming", "outgoing", "both"] = "both",
    relationship_type: str | None = None,
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().entity_related(
        entity_id=entity_id,
        direction=direction,
        relationship_type=relationship_type,
        namespace=namespace,
    )


@tool(
    name="crm_shortest_path",
    description=(
        "Shortest weighted path between two entities "
        "(GET /crm/api/v1/relationships/path/?source_entity_id=&target_entity_id=). Returns directed and undirected paths."
    ),
    tags=_TAGS,
    parameters_model=CrmShortestPathArgs,
)
async def crm_shortest_path(
    from_entity_id: str,
    to_entity_id: str,
    max_depth: int = 10,
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().shortest_path(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        max_depth=max_depth,
        namespace=namespace,
    )
