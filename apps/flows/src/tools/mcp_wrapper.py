"""
MCP Tool Wrapper - обёртка для вызова MCP tools через MCPClient.
"""

from typing import TYPE_CHECKING, override

from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.models.mcp import MCPServerConfig
from apps.flows.src.tools.base import (
    BaseTool,
    ToolArguments,
    ToolParametersSchema,
    ToolResult,
    sanitize_tool_name,
)
from core.integrations.mcp import validate_mcp_parameters_schema
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState


class MCPTool(BaseTool):
    """
    Tool для вызова MCP сервера.

    Вызывает tool на удалённом MCP сервере через MCPClient.
    """

    def __init__(
        self,
        tool_id: str,
        mcp_server_config: MCPServerConfig,
        mcp_tool_name: str,
        *,
        parameters_schema: JsonObject,
        mcp_schema_hash: str,
        mcp_schema_version: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        self.name: str = sanitize_tool_name(tool_id)
        self.description: str = (
            description if description is not None else f"MCP tool: {mcp_tool_name}"
        )
        self._mcp_server_config: MCPServerConfig = mcp_server_config
        self._mcp_tool_name: str = mcp_tool_name
        self._mcp_schema_hash: str = mcp_schema_hash
        self._mcp_schema_version: str = mcp_schema_version
        self._parameters_schema: JsonObject = validate_mcp_parameters_schema(
            require_json_object(
                parameters_schema,
                f"MCPTool.{tool_id}.parameters_schema",
            ),
            f"MCPTool '{tool_id}'",
        )
        self.tags: list[str] = list(tags) if tags is not None else ["mcp"]

    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        """JSON Schema параметров."""
        return self._parameters_schema

    @override
    async def _run_impl(self, args: ToolArguments, state: "ExecutionState") -> ToolResult:
        """
        Вызывает MCP tool на удалённом сервере.

        Args:
            args: Аргументы для MCP tool
            state: ExecutionState агента

        Returns:
            Текстовый результат от MCP tool
        """
        variables = require_json_object(state.variables, "state.variables")

        client = MCPClient(
            config=self._mcp_server_config,
            variables=variables,
            timeout=60.0,
        )

        _ = await client.require_tool_contract(
            self._mcp_tool_name,
            expected_schema_hash=self._mcp_schema_hash,
            expected_schema_version=self._mcp_schema_version,
        )
        result = await client.call_tool(self._mcp_tool_name, args)

        if result.is_error:
            raise MCPClientError(f"MCP tool error: {result.get_text()}")
        if result.structured_content is not None:
            return result.structured_content

        return result.get_text()
