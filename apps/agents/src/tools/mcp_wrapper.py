"""
MCP Tool Wrapper - обёртка для вызова MCP tools через MCPClient.
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from apps.agents.src.clients.mcp_client import MCPClient, MCPClientError
from apps.agents.src.models.mcp import MCPServerConfig
from apps.agents.src.tools.base import BaseTool, CallParameter
from core.logging import get_logger

if TYPE_CHECKING:
    from apps.agents.src.state import ExecutionState

logger = get_logger(__name__)


class MCPTool(BaseTool):
    """
    Tool для вызова MCP сервера.
    
    Вызывает tool на удалённом MCP сервере через MCPClient.
    """
    
    name: str = "mcp_tool"
    description: str = "MCP tool"
    
    def __init__(
        self,
        tool_id: str,
        mcp_server_config: MCPServerConfig,
        mcp_tool_name: str,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, CallParameter]] = None,
        tags: Optional[List[str]] = None,
    ):
        self.name = tool_id
        self.description = description or f"MCP tool: {mcp_tool_name}"
        self._mcp_server_config = mcp_server_config
        self._mcp_tool_name = mcp_tool_name
        self._parameters = parameters or {}
        self.tags = tags or ["mcp"]
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema параметров."""
        if not self._parameters:
            return {"type": "object", "properties": {}, "required": []}
        
        properties = {}
        required = []
        
        for param_name, param in self._parameters.items():
            properties[param_name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.required:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    async def run(self, args: Dict[str, Any], state: "ExecutionState") -> Any:
        """
        Вызывает MCP tool на удалённом сервере.
        
        Args:
            args: Аргументы для MCP tool
            state: ExecutionState агента
            
        Returns:
            Текстовый результат от MCP tool
        """
        # Получаем переменные из state для @var: резолвинга
        variables = state.variables if hasattr(state, 'variables') else {}
        
        client = MCPClient(
            config=self._mcp_server_config,
            variables=variables,
            timeout=60.0,
        )
        
        try:
            result = await client.call_tool(self._mcp_tool_name, args)
            
            if result.is_error:
                return f"MCP tool error: {result.get_text()}"
            
            return result.get_text()
            
        except MCPClientError as e:
            logger.error(f"MCP tool call failed: {e}")
            return f"MCP tool error: {e}"
        except Exception as e:
            logger.error(f"Unexpected error calling MCP tool: {e}")
            return f"MCP tool error: {e}"
