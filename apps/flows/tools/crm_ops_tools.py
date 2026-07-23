"""CRM ops tools for Lara / flow employee (suggests + knowledge-import status)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import quote, urlencode

from pydantic import BaseModel, ConfigDict, Field

from apps.crm.models.api import TaskResponse
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import resolve_namespace_or_raise
from core.pagination import OffsetPage
from core.types import JsonObject, JsonValue, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["crm", "lara", "ops"]


def _require_context_namespace() -> str:
    return resolve_namespace_or_raise()


class CrmListSuggestsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace from session.",
    )
    status: str = Field(
        default="pending",
        description="Suggest status filter (default pending).",
    )
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CrmSuggestIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    suggest_id: str = Field(
        ...,
        min_length=1,
        description="suggest_id from crm_list_suggests. Never invent.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace.",
    )


class CrmKnowledgeImportStatusArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(
        default=None,
        description="Namespace filter; null — active_namespace.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


def _suggest_brief(raw: JsonObject) -> JsonObject:
    suggest_id = raw.get("suggest_id")
    if not isinstance(suggest_id, str) or not suggest_id.strip():
        raise ValueError("suggest response missing suggest_id")
    return {
        "suggest_id": suggest_id,
        "suggest_type": raw.get("suggest_type"),
        "status": raw.get("status"),
        "target_entity_ids": raw.get("target_entity_ids"),
        "payload": raw.get("payload"),
    }


@tool(
    name="crm_list_suggests",
    description=(
        "Lists CRM suggests for a namespace "
        "(GET /crm/api/v1/namespaces/{namespace}/suggests). Default status=pending."
    ),
    tags=_TAGS,
    parameters_model=CrmListSuggestsArgs,
)
async def crm_list_suggests(
    namespace: str | None = None,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    query = urlencode({"status": status, "limit": str(limit), "offset": str(offset)})
    path = f"/crm/api/v1/namespaces/{quote(ns, safe='')}/suggests?{query}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    page_obj = require_json_object(raw, "crm.list_suggests.response")
    items_raw = page_obj.get("items")
    if not isinstance(items_raw, list):
        return json.dumps(
            {"success": False, "error": "crm_list_suggests: items missing"},
            ensure_ascii=False,
        )
    items: list[JsonObject] = []
    for item in items_raw:
        if isinstance(item, dict):
            items.append(_suggest_brief(require_json_object(item, "crm.list_suggests.item")))
    return json.dumps(
        {
            "success": True,
            "namespace": ns,
            "items": items,
            "total": page_obj.get("total"),
            "limit": page_obj.get("limit"),
            "offset": page_obj.get("offset"),
            "count": len(items),
        },
        ensure_ascii=False,
    )


@tool(
    name="crm_resolve_suggest",
    description=(
        "Resolves (accepts) a CRM suggest "
        "(POST /crm/api/v1/namespaces/{namespace}/suggests/{suggest_id}/resolve)."
    ),
    tags=[*_TAGS, "mutation"],
    parameters_model=CrmSuggestIdArgs,
)
async def crm_resolve_suggest(
    suggest_id: str,
    namespace: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    sid = suggest_id.strip()
    if not sid:
        raise ValueError("suggest_id is required")
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    path = (
        f"/crm/api/v1/namespaces/{quote(ns, safe='')}/suggests/"
        f"{quote(sid, safe='')}/resolve"
    )
    client = ServiceClient()
    try:
        raw = await client.post("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    brief = _suggest_brief(require_json_object(raw, "crm.resolve_suggest.response"))
    return json.dumps({"success": True, "suggest": brief}, ensure_ascii=False)


@tool(
    name="crm_dismiss_suggest",
    description=(
        "Dismisses a CRM suggest "
        "(POST /crm/api/v1/namespaces/{namespace}/suggests/{suggest_id}/dismiss)."
    ),
    tags=[*_TAGS, "mutation"],
    parameters_model=CrmSuggestIdArgs,
)
async def crm_dismiss_suggest(
    suggest_id: str,
    namespace: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    sid = suggest_id.strip()
    if not sid:
        raise ValueError("suggest_id is required")
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    path = (
        f"/crm/api/v1/namespaces/{quote(ns, safe='')}/suggests/"
        f"{quote(sid, safe='')}/dismiss"
    )
    client = ServiceClient()
    try:
        raw = await client.post("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    brief = _suggest_brief(require_json_object(raw, "crm.dismiss_suggest.response"))
    return json.dumps({"success": True, "suggest": brief}, ensure_ascii=False)


@tool(
    name="crm_knowledge_import_status",
    description=(
        "Lists knowledge_import CRM tasks for the namespace "
        "(GET /crm/api/v1/tasks?task_type=knowledge_import). "
        "Use when session counters show imports awaiting review or in progress."
    ),
    tags=_TAGS,
    parameters_model=CrmKnowledgeImportStatusArgs,
)
async def crm_knowledge_import_status(
    namespace: str | None = None,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    query = urlencode(
        {
            "namespace": ns,
            "task_type": "knowledge_import",
            "limit": str(limit),
            "offset": str(offset),
        }
    )
    client = ServiceClient()
    try:
        raw = await client.get("crm", f"/crm/api/v1/tasks?{query}")
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = OffsetPage[TaskResponse].model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_knowledge_import_status: invalid response"},
            ensure_ascii=False,
        )
    items: list[JsonObject] = []
    for task in page.items:
        data: JsonValue = task.data
        items.append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "stage": task.stage,
                "progress_pct": task.progress_pct,
                "error_message": task.error_message,
                "namespace": task.namespace,
                "data": data,
            }
        )
    return json.dumps(
        {
            "success": True,
            "namespace": ns,
            "items": items,
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "count": len(items),
        },
        ensure_ascii=False,
    )
