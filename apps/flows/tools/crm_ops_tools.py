"""CRM ops tools — thin wrappers over CrmClient (suggests + knowledge-import status)."""

from __future__ import annotations

from apps.flows.src.tools.decorator import tool
from core.clients.crm_client import CrmClient
from core.clients.crm_models import (
    CrmKnowledgeImportStatusArgs,
    CrmListSuggestsArgs,
    CrmSuggestIdArgs,
)
from core.state import ExecutionState
from core.types import JsonObject

_TAGS = ["crm"]


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_suggests(
        namespace=namespace,
        status=status,
        limit=limit,
        offset=offset,
    )


@tool(
    name="crm_resolve_suggest",
    description=(
        "Resolves (accepts) a CRM suggest "
        "(POST /crm/api/v1/namespaces/{namespace}/suggests/{suggest_id}/resolve)."
    ),
    tags=_TAGS,
    parameters_model=CrmSuggestIdArgs,
)
async def crm_resolve_suggest(
    suggest_id: str,
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().resolve_suggest(suggest_id=suggest_id, namespace=namespace)


@tool(
    name="crm_dismiss_suggest",
    description=(
        "Dismisses a CRM suggest "
        "(POST /crm/api/v1/namespaces/{namespace}/suggests/{suggest_id}/dismiss)."
    ),
    tags=_TAGS,
    parameters_model=CrmSuggestIdArgs,
)
async def crm_dismiss_suggest(
    suggest_id: str,
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().dismiss_suggest(suggest_id=suggest_id, namespace=namespace)


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
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().knowledge_import_status(
        namespace=namespace,
        limit=limit,
        offset=offset,
    )
