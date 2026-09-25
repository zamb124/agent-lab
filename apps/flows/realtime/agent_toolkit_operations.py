"""CRUD AgentToolkit: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.agent.service import build_toolkit_mcp_url_for_frontend
from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.models.agent_toolkit import (
    AgentToolkit,
    AgentToolkitCatalogItem,
    AgentToolkitCatalogListPayload,
    AgentToolkitCreateRequest,
    AgentToolkitDeletedResponse,
    AgentToolkitIdPayload,
    AgentToolkitUpdatePayload,
)
from apps.flows.src.services.agent_toolkit_notify import notify_agent_toolkits_updated
from apps.flows.src.services.agent_toolkit_service import (
    CUSTOM_TOOLKIT_SOURCE,
    PLATFORM_TOOLKIT_SOURCE,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_forbidden,
    raise_not_found,
)

LINNEX_AGENT_DESKTOP_TOOLKIT_ID = "lara"


async def op_flows_agent_toolkits_catalog_list(
    payload: AgentToolkitCatalogListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[AgentToolkitCatalogItem]:
    """Каталог групп инструментов с MCP URL; спаренный desktop (LaraOnly) видит только `lara`."""
    _ = user
    scope = await require_company_member(di)
    _ = await AgentToolkit.ensure_agent_toolkits_bootstrapped(company_id=scope.company_id)
    items: list[AgentToolkitCatalogItem] = []
    for toolkit in await AgentToolkit.list_agent_toolkits():
        is_desktop_toolkit = toolkit.toolkit_id == LINNEX_AGENT_DESKTOP_TOOLKIT_ID
        if payload.desktop_only and not is_desktop_toolkit:
            continue
        items.append(
            AgentToolkitCatalogItem(
                toolkit_id=toolkit.toolkit_id,
                name=toolkit.name,
                description=toolkit.description,
                # Desktop всегда получает lara включённым, даже если в БД компании
                # остался default_enabled=false от старого bootstrap.
                default_enabled=True if is_desktop_toolkit else toolkit.default_enabled,
                position=toolkit.position,
                mcp_url=build_toolkit_mcp_url_for_frontend(toolkit.toolkit_id, payload.frontend_base_url),
            )
        )
    return ListResponse[AgentToolkitCatalogItem](items=items)


async def op_flows_agent_toolkits_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[AgentToolkit]:
    _ = payload, user
    _ = await require_company_member(di)
    return ListResponse[AgentToolkit](
        items=await AgentToolkit.list_agent_toolkits()
    )


async def op_flows_agent_toolkits_item(
    payload: AgentToolkitIdPayload,
    *,
    user: User,
    di: Di,
) -> AgentToolkit:
    _ = user
    _ = await require_company_member(di)
    toolkit = await AgentToolkit.by_toolkit_id(payload.toolkit_id)
    if toolkit is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    return toolkit


async def op_flows_agent_toolkits_create(
    payload: AgentToolkitCreateRequest,
    *,
    user: User,
    di: Di,
) -> AgentToolkit:
    _ = user
    scope = await require_company_member(di)
    existing = await AgentToolkit.by_toolkit_id(payload.toolkit_id)
    if existing is not None:
        raise_conflict(ValueError(f"toolkit {payload.toolkit_id!r} already exists"))
    saved = AgentToolkit(
        toolkit_id=payload.toolkit_id,
        name=payload.name,
        description=payload.description,
        default_enabled=payload.default_enabled,
        position=payload.position,
        flow_ids=list(payload.flow_ids),
        tool_ids=list(payload.tool_ids),
        source=CUSTOM_TOOLKIT_SOURCE,
    )
    _ = await AgentToolkit.set(saved)
    await notify_agent_toolkits_updated(di.redis_client, scope.company_id)
    return saved


async def op_flows_agent_toolkits_update(
    payload: AgentToolkitUpdatePayload,
    *,
    user: User,
    di: Di,
) -> AgentToolkit:
    _ = user
    scope = await require_company_member(di)
    existing = await AgentToolkit.by_toolkit_id(payload.toolkit_id)
    if existing is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    saved = existing.model_copy(
        update={
            "name": payload.name,
            "description": payload.description,
            "default_enabled": payload.default_enabled,
            "position": payload.position,
            "flow_ids": list(payload.flow_ids),
            "tool_ids": list(payload.tool_ids),
        },
    )
    _ = await AgentToolkit.set(saved)
    await notify_agent_toolkits_updated(di.redis_client, scope.company_id)
    return saved


async def op_flows_agent_toolkits_remove(
    payload: AgentToolkitIdPayload,
    *,
    user: User,
    di: Di,
) -> AgentToolkitDeletedResponse:
    _ = user
    scope = await require_company_member(di)
    existing = await AgentToolkit.by_toolkit_id(payload.toolkit_id)
    if existing is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    if existing.source == PLATFORM_TOOLKIT_SOURCE:
        raise_forbidden(PermissionError("platform toolkit cannot be deleted"))
    _ = await AgentToolkit.delete_by_toolkit_id(payload.toolkit_id)
    await notify_agent_toolkits_updated(di.redis_client, scope.company_id)
    return AgentToolkitDeletedResponse(status="deleted", toolkit_id=payload.toolkit_id)
