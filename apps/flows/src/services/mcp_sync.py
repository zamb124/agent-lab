"""
Синхронизация MCP tools в tool_repository.

Единая точка для UI (`POST .../mcp/servers/{id}/sync`), фоновой инициализации компании
и любых других вызовов: один контракт записи `ToolReference` и очистки `cached_tools`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.mcp import MCPDiscoveredTool, MCPServerConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.services.mcp_defaults import build_default_mcp_servers
from core.context import get_context
from core.integrations.mcp import mcp_tool_reference_id
from core.logging import get_logger

if TYPE_CHECKING:
    from apps.flows.src.container_contracts import FlowRuntimeContainer

logger = get_logger(__name__)


def _mcp_headers_need_variables(server_config: MCPServerConfig) -> bool:
    return any("@var:" in str(v) for v in server_config.headers.values())


async def resolve_mcp_client_variables(
    container: FlowRuntimeContainer,
    server_config: MCPServerConfig,
) -> dict[str, str]:
    """Переменные для MCPClient: @var: headers и platform context propagation."""
    variables: dict[str, str] = {}
    if _mcp_headers_need_variables(server_config):
        resolved_map = await container.variables_service.get_company_variables_map()
        variables = {
            key: value if isinstance(value, str) else str(value)
            for key, value in resolved_map.items()
        }
    if server_config.propagate_platform_context:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MCPClientError(
                "Platform MCP requires authenticated user and company context"
            )
        variables = dict(variables)
        variables["company_id"] = ctx.active_company.company_id
        variables["user_id"] = ctx.user.user_id
    return variables


async def sync_mcp_server_tools(
    *,
    container: FlowRuntimeContainer,
    server_config: MCPServerConfig,
) -> tuple[list[str], list[MCPDiscoveredTool]]:
    """
    Запрашивает tools/list у MCP сервера и upsert'ит их как ToolReference (code_mode=mcp_tool).

    Удаляет из `tool_repository` записи, которые были в `server_config.cached_tools`,
    но больше не пришли с сервера (как при ручном sync из UI).

    Возвращает (tool_ids, список инструментов с MCP) для HTTP-ответа и логов.
    """
    variables = await resolve_mcp_client_variables(container, server_config)
    client = MCPClient(server_config, variables=variables)
    _ = await client.initialize()
    tools = await client.list_tools()

    server_id = server_config.server_id
    previous_cached = list(server_config.cached_tools)
    tool_ids: list[str] = []

    for t in tools:
        tool_id = mcp_tool_reference_id(server_id, t.tool_name)
        tool_ids.append(tool_id)
        description = t.description if t.description is not None else f"MCP tool: {t.tool_name}"
        _ = await container.tool_repository.set(
            ToolReference(
                tool_id=tool_id,
                title=t.title if t.title is not None else t.tool_name,
                description=description,
                parameters_schema=t.parameters_schema,
                code_mode=CodeMode.MCP_TOOL,
                mcp_server_id=server_id,
                mcp_tool_name=t.tool_name,
                mcp_schema_hash=t.schema_hash,
                mcp_schema_version=t.schema_version,
                mcp_output_schema=t.output_schema,
                mcp_annotations=t.annotations,
                mcp_execution=t.execution,
                tags=["mcp", f"mcp:{server_id}"],
            )
        )

    for old_tool_id in previous_cached:
        if old_tool_id not in tool_ids:
            _ = await container.tool_repository.delete(old_tool_id)

    server_config.cached_tools = tool_ids
    server_config.last_sync_at = datetime.now(tz=timezone.utc)
    _ = await container.mcp_server_repository.set(server_config)

    logger.info(
        "MCP server synced: server_id=%s tools=%s",
        server_id,
        len(tool_ids),
    )
    return tool_ids, tools


async def ensure_default_mcp_servers_for_company(
    *,
    container: FlowRuntimeContainer,
) -> list[MCPServerConfig]:
    """
    Upsert'ит дефолтные MCP серверы компании в mcp_server_repository.
    """
    servers = build_default_mcp_servers()
    for s in servers:
        _ = await container.mcp_server_repository.set(s)
    return servers


async def sync_auto_mcp_servers_for_company(*, container: FlowRuntimeContainer) -> dict[str, int]:
    """
    Синхронизирует tools для всех активных MCP серверов компании.
    """
    servers = await container.mcp_server_repository.list_active()
    synced = 0
    tools_total = 0
    failed = 0
    for srv in servers:
        try:
            tool_ids, _ = await sync_mcp_server_tools(container=container, server_config=srv)
        except Exception as exc:
            failed += 1
            logger.warning(
                "MCP server auto-sync skipped: server_id=%s error=%s",
                srv.server_id,
                exc,
                exc_info=True,
            )
            continue
        synced += 1
        tools_total += len(tool_ids)
    return {"servers": synced, "tools": tools_total, "failed": failed}
