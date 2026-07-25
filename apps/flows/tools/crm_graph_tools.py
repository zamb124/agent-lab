"""CRM graph tools for Lara / flow employee (relationships + neighborhood)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, Literal
from urllib.parse import quote, urlencode

from pydantic import BaseModel, ConfigDict, Field

from apps.crm.models.api import RelationshipResponse, RelationshipTypeResponse
from apps.crm.models.graph import RelatedEntitiesResponse, ShortestPathResponse
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import resolve_namespace_or_raise
from core.pagination import CursorPage, OffsetPage
from core.types import require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["crm"]


def _require_context_namespace() -> str:
    return resolve_namespace_or_raise()


class CrmListRelationshipsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str | None = Field(
        default=None,
        description="Filter edges where entity is source or target. Prefer when browsing one node.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace filter; null — active_namespace from session.",
    )
    limit: int = Field(default=200, ge=1, le=1000, description="Page size when listing company-wide.")
    cursor: str | None = Field(default=None, description="Opaque next_cursor from previous page.")


class CrmDeleteRelationshipArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    relationship_id: str = Field(
        ...,
        min_length=1,
        description="relationship_id from crm_list_relationships / create. Never invent.",
    )


class CrmListRelationshipTypesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CrmEntityRelatedArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="Center entity_id. Never invent.")
    direction: Literal["incoming", "outgoing", "both"] = Field(
        default="both",
        description="Edge direction filter.",
    )
    relationship_type: str | None = Field(
        default=None,
        description="Optional relationship_type type_id filter.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace for traversal filter; null — active_namespace.",
    )


class CrmShortestPathArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    from_entity_id: str = Field(..., min_length=1, description="Start entity_id.")
    to_entity_id: str = Field(..., min_length=1, description="End entity_id.")
    max_depth: int = Field(default=10, ge=1, le=20, description="Max path depth.")
    namespace: str | None = Field(
        default=None,
        description="Namespace for traversal; null — active_namespace.",
    )


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
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    query: dict[str, str] = {"namespace": ns, "limit": str(limit)}
    if entity_id is not None and str(entity_id).strip():
        query["entity_id"] = entity_id.strip()
    if cursor is not None and str(cursor).strip():
        query["cursor"] = cursor.strip()
    path = f"/crm/api/v1/relationships?{urlencode(query)}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = CursorPage[RelationshipResponse].model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_list_relationships: invalid response"},
            ensure_ascii=False,
        )
    items = [
        require_json_object(item.model_dump(mode="json"), "crm.list_relationships.item")
        for item in page.items
    ]
    return json.dumps(
        {
            "success": True,
            "items": items,
            "next_cursor": page.next_cursor,
            "has_more": page.has_more,
            "count": len(items),
        },
        ensure_ascii=False,
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
async def crm_delete_relationship(relationship_id: str, *, state: "ExecutionState") -> str:
    _ = state
    rid = relationship_id.strip()
    if not rid:
        raise ValueError("relationship_id is required")
    client = ServiceClient()
    try:
        _ = await client.delete("crm", f"/crm/api/v1/relationships/{quote(rid, safe='')}")
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(
        {"success": True, "relationship_id": rid, "status": "deleted"},
        ensure_ascii=False,
    )


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
    state: "ExecutionState",
) -> str:
    _ = state
    path = f"/crm/api/v1/relationships/types/?limit={limit}&offset={offset}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = OffsetPage[RelationshipTypeResponse].model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_list_relationship_types: invalid response"},
            ensure_ascii=False,
        )
    compact = [
        {
            "type_id": item.type_id,
            "name": item.name,
            "is_directed": item.is_directed,
            "inverse_type_id": item.inverse_type_id,
        }
        for item in page.items
    ]
    return json.dumps(
        {
            "success": True,
            "items": compact,
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "count": len(compact),
        },
        ensure_ascii=False,
    )


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
    state: "ExecutionState",
) -> str:
    _ = state
    eid = entity_id.strip()
    if not eid:
        raise ValueError("entity_id is required")
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    query: dict[str, str] = {"direction": direction, "namespace": ns}
    if relationship_type is not None and str(relationship_type).strip():
        query["relationship_type"] = relationship_type.strip()
    path = f"/crm/api/v1/entities/{quote(eid, safe='')}/related?{urlencode(query)}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        related = RelatedEntitiesResponse.model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_entity_related: invalid response"},
            ensure_ascii=False,
        )
    payload = require_json_object(related.model_dump(mode="json"), "crm.entity_related")
    return json.dumps({"success": True, "related": payload}, ensure_ascii=False)


@tool(
    name="crm_shortest_path",
    description=(
        "Shortest weighted path between two entities "
        "(GET /crm/api/v1/relationships/path/?from=&to=). Returns directed and undirected paths."
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
    state: "ExecutionState",
) -> str:
    _ = state
    src = from_entity_id.strip()
    dst = to_entity_id.strip()
    if not src or not dst:
        raise ValueError("from_entity_id and to_entity_id are required")
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    query = {
        "from": src,
        "to": dst,
        "max_depth": str(max_depth),
        "namespace": ns,
    }
    path = f"/crm/api/v1/relationships/path/?{urlencode(query)}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        result = ShortestPathResponse.model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_shortest_path: invalid response"},
            ensure_ascii=False,
        )
    payload = require_json_object(result.model_dump(mode="json"), "crm.shortest_path")
    return json.dumps({"success": True, "path": payload}, ensure_ascii=False)
