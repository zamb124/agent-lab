"""
Синхронизация MCP tools в tool_repository.

Единая точка для UI (`POST .../mcp/servers/{id}/sync`), фоновой инициализации компании
и любых других вызовов: один контракт записи `ToolReference` и очистки `cached_tools`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.mcp import MCPDiscoveredTool, MCPServerConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.mcp_client import MCPClient, MCPClientError
from apps.flows.src.services.mcp_defaults import build_default_mcp_servers
from apps.flows.tools.builtin_specs import require_not_builtin_tool_id
from core.context import get_context, require_active_company
from core.integrations.mcp import mcp_tool_reference_id
from core.logging import get_logger
from core.variables.service import VariablesService

logger = get_logger(__name__)


def _mcp_headers_need_variables(server_config: MCPServerConfig) -> bool:
    return any("@var:" in str(v) for v in server_config.headers.values())


async def resolve_mcp_client_variables(
    variables_service: VariablesService,
    server_config: MCPServerConfig,
) -> dict[str, str]:
    """Переменные для MCPClient: @var: headers и platform context propagation."""
    variables: dict[str, str] = {}
    if _mcp_headers_need_variables(server_config):
        resolved_map = await variables_service.get_company_variables_map()
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
    variables_service: VariablesService,
    flow_access_service: FlowAccessService,
    server_config: MCPServerConfig,
) -> tuple[list[str], list[MCPDiscoveredTool]]:
    """
    Запрашивает tools/list у MCP сервера и upsert'ит их как ToolReference (code_mode=mcp_tool).

    Удаляет из `tool_repository` записи, которые были в `server_config.cached_tools`,
    но больше не пришли с сервера (как при ручном sync из UI).

    Возвращает (tool_ids, список инструментов с MCP) для HTTP-ответа и логов.
    """
    variables = await resolve_mcp_client_variables(variables_service, server_config)
    client = MCPClient(server_config, variables=variables)
    _ = await client.initialize()
    tools = await client.list_tools()

    server_id = server_config.server_id
    previous_cached = list(server_config.cached_tools)
    tool_ids: list[str] = []
    company = require_active_company()

    for t in tools:
        tool_id = mcp_tool_reference_id(server_id, t.tool_name)
        tool_ids.append(tool_id)
        description = t.description if t.description is not None else f"MCP tool: {t.tool_name}"
        tool_ref = ToolReference(
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
        _ = await ToolReference.set(tool_ref)
        await flow_access_service.sync_tool_saved(
            tool_id,
            company_id=company.company_id,
            permission=tool_ref.permission,
        )

    for old_tool_id in previous_cached:
        if old_tool_id not in tool_ids:
            require_not_builtin_tool_id(old_tool_id, source="mcp cached_tools")
            _ = await ToolReference.delete_by_id(ToolReference.row_id(old_tool_id))
            await flow_access_service.sync_tool_deleted(
                old_tool_id, company_id=company.company_id
            )

    server_config.cached_tools = tool_ids
    server_config.last_sync_at = datetime.now(tz=timezone.utc)
    _ = await MCPServerConfig.set(server_config)

    logger.info("flows.mcp.server.synced.server_id.tools", server_id=server_id, tools=len(tool_ids))
    return tool_ids, tools


async def ensure_default_mcp_servers_for_company() -> list[MCPServerConfig]:
    """
    Upsert'ит дефолтные MCP серверы компании.
    """
    servers = build_default_mcp_servers()
    for s in servers:
        _ = await MCPServerConfig.set(s)
    return servers


async def sync_auto_mcp_servers_for_company(
    *,
    variables_service: VariablesService,
    flow_access_service: FlowAccessService,
) -> dict[str, int]:
    """
    Синхронизирует tools для всех активных MCP серверов компании.
    """
    servers = [
        server
        for server in await MCPServerConfig.list(limit=1000)
        if server.is_active
    ]
    synced = 0
    tools_total = 0
    failed = 0
    for srv in servers:
        try:
            tool_ids, _ = await sync_mcp_server_tools(
                variables_service=variables_service,
                flow_access_service=flow_access_service,
                server_config=srv,
            )
        except Exception as exc:
            failed += 1
            logger.warning(
                "flows.mcp.server.auto.sync.skipped",
                server_id=srv.server_id,
                error=exc,
                exc_info=True,
            )
            continue
        synced += 1
        tools_total += len(tool_ids)
    return {"servers": synced, "tools": tools_total, "failed": failed}
