"""MCP stamp executor for DatasourceProtocol."""

from __future__ import annotations

from time import perf_counter

from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.container_contracts import FlowRuntimeContainer
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectorSpec,
    DatasourceExecuteResult,
    DatasourceOperation,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceTestResult,
)
from core.types import JsonObject, require_json_object


class DatasourceMcpExecutor:
    def __init__(self, container: FlowRuntimeContainer) -> None:
        self._container: FlowRuntimeContainer = container

    async def run(
        self,
        *,
        spec: DatasourceConnectorSpec,
        connection: DatasourceConnection,
        operation: DatasourceOperation,
        sql: str | None,
        params: JsonObject,
        password: str | None,
        as_test: bool,
    ) -> (
        DatasourceSchemaSnapshot
        | DatasourceQueryResult
        | DatasourceExecuteResult
        | DatasourceTestResult
    ):
        _ = password
        server_id = connection.mcp_server_id or spec.mcp_server_id
        if server_id is None or not server_id.strip():
            raise ValueError("mcp datasource requires mcp_server_id")
        tool_name = _mcp_tool_name(spec, operation, as_test=as_test)
        server = await self._container.mcp_server_repository.get(server_id)
        if server is None:
            raise ValueError(f"MCP server not found: {server_id}")
        arguments: JsonObject = {
            "operation": operation.value,
            "datasource_id": connection.datasource_id,
            "as_test": as_test,
            "params": params,
        }
        if sql is not None:
            arguments["sql"] = sql
        started = perf_counter()
        client = MCPClient(server, {})
        try:
            result = await client.call_tool(tool_name, arguments)
        except MCPClientError as exc:
            raise ValueError(str(exc)) from exc
        if result.is_error:
            raise ValueError(f"mcp datasource tool error: {result.content!r}")
        latency_ms = int((perf_counter() - started) * 1000)
        if as_test:
            return DatasourceTestResult(ok=True, latency_ms=latency_ms)
        payload = result.structured_content
        if payload is None:
            raise ValueError("mcp datasource tool must return structuredContent")
        body = require_json_object(payload, "mcp.datasource.structured_content")
        match operation:
            case DatasourceOperation.INTROSPECT:
                return DatasourceSchemaSnapshot.model_validate(body)
            case DatasourceOperation.QUERY:
                return DatasourceQueryResult.model_validate(body)
            case DatasourceOperation.EXECUTE:
                return DatasourceExecuteResult.model_validate(body)


def _mcp_tool_name(
    spec: DatasourceConnectorSpec,
    operation: DatasourceOperation,
    *,
    as_test: bool,
) -> str:
    resolved = DatasourceOperation.INTROSPECT if as_test else operation
    match resolved:
        case DatasourceOperation.INTROSPECT:
            tool = spec.mcp_introspect_tool or spec.mcp_query_tool
            if tool is None or not tool.strip():
                raise ValueError("mcp datasource requires mcp_query_tool")
            return tool
        case DatasourceOperation.QUERY:
            tool = spec.mcp_query_tool
            if tool is None or not tool.strip():
                raise ValueError("mcp datasource requires mcp_query_tool")
            return tool
        case DatasourceOperation.EXECUTE:
            tool = spec.mcp_execute_tool
            if tool is None or not tool.strip():
                raise ValueError("mcp datasource execute requires mcp_execute_tool")
            return tool
