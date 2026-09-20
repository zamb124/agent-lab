"""CRUD AgentToolkit: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import (
    FlowsEmptyPayload,
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.agent_toolkit import (
    AgentToolkit,
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
    get_agent_toolkit,
    list_agent_toolkits,
    save_agent_toolkit,
)
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import (
    raise_conflict,
    raise_forbidden,
    raise_not_found,
)


async def op_flows_agent_toolkits_list(
    payload: FlowsEmptyPayload,
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
        raise_not_found(LookupError(f"Toolkit {payload.toolkit_id!r} не найден"))
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
        raise_conflict(ValueError(f"Toolkit {payload.toolkit_id!r} уже существует"))
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
        raise_not_found(LookupError(f"Toolkit {payload.toolkit_id!r} не найден"))
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
        raise_not_found(LookupError(f"Toolkit {payload.toolkit_id!r} не найден"))
    if existing.source == PLATFORM_TOOLKIT_SOURCE:
        raise_forbidden(PermissionError("Platform toolkit нельзя удалить"))
    await delete_agent_toolkit(container.agent_toolkit_repository, payload.toolkit_id)
    await notify_agent_toolkits_updated(container.redis_client, scope.company_id)
    return AgentToolkitDeletedResponse(status="deleted", toolkit_id=payload.toolkit_id)
