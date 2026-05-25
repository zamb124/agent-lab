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
from core.logging import get_logger
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


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
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        self.name: str = sanitize_tool_name(tool_id)
        self.description: str = description or f"MCP tool: {mcp_tool_name}"
        self._mcp_server_config: MCPServerConfig = mcp_server_config
        self._mcp_tool_name: str = mcp_tool_name
        self._parameters_schema: JsonObject = require_json_object(
            parameters_schema,
            f"MCPTool.{tool_id}.parameters_schema",
        )
        if self._parameters_schema.get("type") != "object" or not isinstance(
            self._parameters_schema.get("properties"), dict
        ):
            raise ValueError(f"MCPTool '{tool_id}' parameters_schema must be object JSON Schema")
        self.tags: list[str] = tags or ["mcp"]

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

        try:
            result = await client.call_tool(self._mcp_tool_name, args)
        except MCPClientError as e:
            logger.error(f"MCP tool call failed: {e}")
            return f"MCP tool error: {e}"

        if result.is_error:
            return f"MCP tool error: {result.get_text()}"

        return result.get_text()
