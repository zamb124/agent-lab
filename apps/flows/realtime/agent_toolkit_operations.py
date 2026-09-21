"""CRUD AgentToolkit: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.agent.service import build_toolkit_mcp_url_for_frontend
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
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
    delete_agent_toolkit,
    ensure_agent_toolkits_bootstrapped,
    get_agent_toolkit,
    list_agent_toolkits,
    save_agent_toolkit,
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
    container: FlowContainer,
) -> ListResponse[AgentToolkitCatalogItem]:
    """Каталог групп инструментов с MCP URL; спаренный desktop (LaraOnly) видит только `lara`."""
    _ = user
    scope = await require_company_member(container)
    _ = await ensure_agent_toolkits_bootstrapped(
        container.agent_toolkit_repository, company_id=scope.company_id
    )
    items: list[AgentToolkitCatalogItem] = []
    for toolkit in await list_agent_toolkits(container.agent_toolkit_repository):
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
    container: FlowContainer,
) -> ListResponse[AgentToolkit]:
    _ = payload, user
    _ = await require_company_member(container)
    return ListResponse[AgentToolkit](
        items=await list_agent_toolkits(container.agent_toolkit_repository)
    )


async def op_flows_agent_toolkits_item(
    payload: AgentToolkitIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentToolkit:
    _ = user
    _ = await require_company_member(container)
    toolkit = await get_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    if toolkit is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    return toolkit


async def op_flows_agent_toolkits_create(
    payload: AgentToolkitCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> AgentToolkit:
    _ = user
    scope = await require_company_member(container)
    existing = await get_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    if existing is not None:
        raise_conflict(ValueError(f"toolkit {payload.toolkit_id!r} already exists"))
    saved = await save_agent_toolkit(
        container.agent_toolkit_repository,
        AgentToolkit(
            toolkit_id=payload.toolkit_id,
            name=payload.name,
            description=payload.description,
            default_enabled=payload.default_enabled,
            position=payload.position,
            flow_ids=list(payload.flow_ids),
            tool_ids=list(payload.tool_ids),
            source=CUSTOM_TOOLKIT_SOURCE,
        ),
    )
    await notify_agent_toolkits_updated(container.redis_client, scope.company_id)
    return saved


async def op_flows_agent_toolkits_update(
    payload: AgentToolkitUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentToolkit:
    _ = user
    scope = await require_company_member(container)
    existing = await get_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    if existing is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    saved = await save_agent_toolkit(
        container.agent_toolkit_repository,
        existing.model_copy(
            update={
                "name": payload.name,
                "description": payload.description,
                "default_enabled": payload.default_enabled,
                "position": payload.position,
                "flow_ids": list(payload.flow_ids),
                "tool_ids": list(payload.tool_ids),
            }
        ),
    )
    await notify_agent_toolkits_updated(container.redis_client, scope.company_id)
    return saved


async def op_flows_agent_toolkits_remove(
    payload: AgentToolkitIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentToolkitDeletedResponse:
    _ = user
    scope = await require_company_member(container)
    existing = await get_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    if existing is None:
        raise_not_found(LookupError(f"toolkit {payload.toolkit_id!r} not found"))
    if existing.source == PLATFORM_TOOLKIT_SOURCE:
        raise_forbidden(PermissionError("platform toolkit cannot be deleted"))
    await delete_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    await notify_agent_toolkits_updated(container.redis_client, scope.company_id)
    return AgentToolkitDeletedResponse(status="deleted", toolkit_id=payload.toolkit_id)
