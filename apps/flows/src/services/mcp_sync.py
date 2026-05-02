"""
Синхронизация MCP tools в tool_repository.

Единая точка для UI (`POST .../mcp/servers/{id}/sync`), фоновой инициализации компании
и любых других вызовов: один контракт записи `ToolReference` и очистки `cached_tools`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from apps.flows.src.clients.mcp_client import MCPClient
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.mcp import MCPServerConfig, MCPToolInfo
from apps.flows.src.models.tool_reference import ToolReference
from core.logging import get_logger
from apps.flows.src.services.mcp_defaults import build_default_mcp_servers


logger = get_logger(__name__)


def _mcp_tool_id(server_id: str, tool_name: str) -> str:
    sid = str(server_id).strip()
    tname = str(tool_name).strip()
    if not sid:
        raise ValueError("server_id обязателен")
    if not tname:
        raise ValueError("tool_name обязателен")
    return f"mcp:{sid}:{tname}"


def _mcp_headers_need_variables(server_config: MCPServerConfig) -> bool:
    return any("@var:" in str(v) for v in server_config.headers.values())


async def _mcp_resolved_variables(
    container: FlowContainer, server_config: MCPServerConfig
) -> dict[str, str]:
    if not _mcp_headers_need_variables(server_config):
        return {}
    return await container.variables_service.get_all_resolved_vars()


async def sync_mcp_server_tools(
    *,
    container: FlowContainer,
    server_config: MCPServerConfig,
) -> tuple[list[str], list[MCPToolInfo]]:
    """
    Запрашивает tools/list у MCP сервера и upsert'ит их как ToolReference (code_mode=mcp_tool).

    Удаляет из `tool_repository` записи, которые были в `server_config.cached_tools`,
    но больше не пришли с сервера (как при ручном sync из UI).

    Возвращает (tool_ids, список инструментов с MCP) для HTTP-ответа и логов.
    """
    variables = await _mcp_resolved_variables(container, server_config)
    client = MCPClient(server_config, variables=variables)
    await client.initialize()
    tools = await client.list_tools()

    server_id = server_config.server_id
    previous_cached = list(server_config.cached_tools)
    tool_ids: list[str] = []

    for t in tools:
        tool_id = _mcp_tool_id(server_id, t.name)
        tool_ids.append(tool_id)
        description = t.description if (t.description and str(t.description).strip()) else f"MCP tool: {t.name}"
        await container.tool_repository.set(
            ToolReference(
                tool_id=tool_id,
                title=t.name,
                description=description,
                parameters_schema=t.input_schema,
                code_mode=CodeMode.MCP_TOOL,
                mcp_server_id=server_id,
                mcp_tool_name=t.name,
                tags=["mcp", f"mcp:{server_id}"],
            )
        )

    for old_tool_id in previous_cached:
        if old_tool_id not in tool_ids:
            await container.tool_repository.delete(old_tool_id)

    server_config.cached_tools = tool_ids
    server_config.last_sync_at = datetime.now(tz=timezone.utc)
    await container.mcp_server_repository.set(server_config)

    logger.info(
        "MCP server synced: server_id=%s tools=%s",
        server_id,
        len(tool_ids),
    )
    return tool_ids, tools


async def ensure_default_mcp_servers_for_company(*, container: FlowContainer) -> list[MCPServerConfig]:
    """
    Upsert'ит дефолтные MCP серверы компании в mcp_server_repository.
    """
    servers = build_default_mcp_servers()
    for s in servers:
        await container.mcp_server_repository.set(s)
    return servers


async def sync_auto_mcp_servers_for_company(*, container: FlowContainer) -> dict[str, int]:
    """
    Синхронизирует tools для всех активных MCP серверов компании.
    """
    servers = await container.mcp_server_repository.list_active()
    synced = 0
    tools_total = 0
    for srv in servers:
        tool_ids, _ = await sync_mcp_server_tools(container=container, server_config=srv)
        synced += 1
        tools_total += len(tool_ids)
    return {"servers": synced, "tools": tools_total}

