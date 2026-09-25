"""Сервис групп инструментов HumanitecAgent."""

from __future__ import annotations

from apps.flows.src.models.agent_toolkit import AgentToolkit

PLATFORM_TOOLKIT_SOURCE = "platform"
CUSTOM_TOOLKIT_SOURCE = "custom"


async def resolve_allowed_flow_ids(
    *,
    toolkit_id: str | None,
) -> set[str]:
    allowed: set[str] = set()
    for toolkit in await AgentToolkit.list_agent_toolkits():
        if toolkit_id is not None and toolkit.toolkit_id != toolkit_id:
            continue
        allowed.update(toolkit.flow_ids)
    return allowed


async def resolve_allowed_tool_ids(
    *,
    toolkit_id: str | None,
) -> set[str]:
    allowed: set[str] = set()
    for toolkit in await AgentToolkit.list_agent_toolkits():
        if toolkit_id is not None and toolkit.toolkit_id != toolkit_id:
            continue
        allowed.update(toolkit.tool_ids)
    return allowed


async def is_flow_in_agent_toolkits(flow_id: str) -> bool:
    for toolkit in await AgentToolkit.list_agent_toolkits():
        if flow_id in toolkit.flow_ids:
            return True
    return False


async def is_tool_in_agent_toolkits(tool_id: str) -> bool:
    for toolkit in await AgentToolkit.list_agent_toolkits():
        if tool_id in toolkit.tool_ids:
            return True
    return False
