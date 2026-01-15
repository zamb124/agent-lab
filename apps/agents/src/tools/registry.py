"""
ToolRegistry - реестр инструментов.

Zero-Guess Architecture:
- Единственная точка создания и получения tools
- Все tools регистрируются явно
- Нет ToolFactory - логика перенесена сюда
"""

from typing import Any, Dict, List, Optional, Union

from core.logging import get_logger
from apps.agents.src.models import ToolReference
from apps.agents.src.models.enums import CodeMode, NodeType
from apps.agents.src.models.tool_reference import CallParameter
from apps.agents.src.tools.base import BaseTool, InlineTool, ToolType
from apps.agents.src.tools.mcp_wrapper import MCPTool

logger = get_logger(__name__)


class ToolRegistry:
    """
    Реестр инструментов.
    
    Единая точка для:
    - Регистрации builtin tools
    - Создания inline tools из конфигов
    - Создания node-as-tool wrappers
    - Получения tools по имени
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._initialized = False

    def register(self, tool: BaseTool) -> None:
        """Регистрирует tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Tool зарегистрирован: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Получает tool по имени."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Проверяет зарегистрирован ли tool."""
        return name in self._tools

    def list_all(self) -> Dict[str, BaseTool]:
        """Возвращает все зарегистрированные tools."""
        return dict(self._tools)

    def register_builtin_tools(self) -> None:
        """Регистрирует встроенные tools."""
        if self._initialized:
            return

        from apps.agents.tools import (
            calculator,
            final_answer,
            finish,
            nsis_api,
            vision_analyze,
            reason,
            self_check,
            ask_user,
            schedule_cron_task,
            schedule_interval_task,
            schedule_one_time_task,
            list_scheduled_tasks,
            cancel_scheduled_task,
        )

        builtin_tools = [
            calculator,
            final_answer,
            finish,
            nsis_api,
            vision_analyze,
            reason,
            self_check,
            ask_user,
            schedule_cron_task,
            schedule_interval_task,
            schedule_one_time_task,
            list_scheduled_tasks,
            cancel_scheduled_task,
        ]

        for tool in builtin_tools:
            self.register(tool)

        self._initialized = True
        logger.info(f"Зарегистрировано {len(builtin_tools)} встроенных tools")

    # =========================================================================
    # Методы создания tools
    # =========================================================================

    async def create_tool(self, tool_ref: Union[str, Dict[str, Any]]) -> BaseTool:
        """
        Создает tool из inline конфига.

        Args:
            tool_ref: inline конфиг (dict) с полным кодом

        Returns:
            BaseTool

        Raises:
            ValueError: если tool_ref - строка или отсутствует code
        """
        if isinstance(tool_ref, str):
            raise ValueError(
                f"Tool '{tool_ref}' passed as string. All tools must be inline with code. "
                f"Agent must be assembled with AgentsLoader which inlines all tools."
            )
        
        if not isinstance(tool_ref, dict):
            raise ValueError(f"Tool ref must be dict with inline code, got {type(tool_ref)}")
        
        # react_node как tool - используем NodeAsToolWrapper
        if tool_ref.get("type") == NodeType.REACT_NODE.value or tool_ref.get("prompt"):
            return self._create_node_as_tool(tool_ref)
        
        # MCP tool - создаём MCPTool
        code_mode = tool_ref.get("code_mode")
        if code_mode == CodeMode.MCP_TOOL.value or code_mode == CodeMode.MCP_TOOL:
            return await self._create_mcp_tool(tool_ref)
        
        code = tool_ref.get("code")
        if not code:
            raise ValueError(f"Tool config requires 'code' field: {tool_ref}")
        return self._create_inline_tool_from_config(tool_ref)

    async def create_tools(
        self, tool_refs: List[Union[str, Dict[str, Any], ToolReference]]
    ) -> List[BaseTool]:
        """
        Создает список tools из inline конфигов.
        
        Для builtin tools (FunctionTool) возвращает зарегистрированный инстанс.
        Для inline tools создает InlineTool из кода.

        Args:
            tool_refs: Список dict-конфигов или ToolReference

        Returns:
            Список BaseTool
        """
        tools = []

        for ref in tool_refs:
            tool = None
            if isinstance(ref, dict):
                tool_id = ref.get("tool_id")
                # Сначала проверяем builtin tools (FunctionTool)
                if tool_id:
                    builtin = self.get(tool_id)
                    if builtin:
                        tool = builtin
                    else:
                        tool = await self.create_tool(ref)
                else:
                    tool = await self.create_tool(ref)
            elif isinstance(ref, ToolReference):
                # Сначала проверяем builtin
                builtin = self.get(ref.tool_id)
                if builtin:
                    tool = builtin
                elif not ref.code:
                    raise ValueError(f"ToolReference '{ref.tool_id}' requires 'code' field")
                else:
                    tool = self._create_inline_tool_from_reference(ref)
            elif isinstance(ref, str):
                raise ValueError(
                    f"Tool '{ref}' passed as string. All tools must be inline with code. "
                    f"Agent must be assembled with AgentsLoader which inlines all tools."
                )
            else:
                raise ValueError(f"Unknown tool ref type: {type(ref)}")

            tools.append(tool)

        return tools

    def _create_inline_tool_from_config(self, config: Dict[str, Any]) -> BaseTool:
        """
        Создает InlineTool из inline конфига.

        Args:
            config: {
                "tool_id": "my_tool",
                "description": "...",
                "args_schema": {"param": {"type": "string", "description": "..."}},
                "code": "def execute(args, state): ..."
            }

        Returns:
            InlineTool
        """
        tool_id = config.get("tool_id", "inline_tool")
        code = config.get("code")
        if not code:
            raise ValueError(f"Inline tool '{tool_id}' requires 'code' field")

        parameters = None
        args_schema = config.get("args_schema")
        if args_schema:
            parameters = {}
            for name, schema in args_schema.items():
                if isinstance(schema, CallParameter):
                    parameters[name] = schema
                else:
                    parameters[name] = CallParameter(
                        type=schema.get("type", "string"),
                        description=schema.get("description", ""),
                    )

        tool_type_str = config.get("tool_type", "tool")
        tool_type = ToolType(tool_type_str) if isinstance(tool_type_str, str) else tool_type_str

        tool = InlineTool(
            tool_id=tool_id,
            code=code,
            title=config.get("title"),
            description=config.get("description"),
            parameters=parameters,
            tool_type=tool_type,
        )
        
        self.register(tool)
        return tool

    async def _create_mcp_tool(self, config: Dict[str, Any]) -> BaseTool:
        """
        Создает MCPTool из конфига.

        Args:
            config: {
                "tool_id": "mcp:server:tool",
                "description": "...",
                "args_schema": {...},
                "mcp_server_id": "server_id",
                "mcp_tool_name": "tool_name"
            }

        Returns:
            MCPTool
        """
        from apps.agents.src.container import get_container
        
        tool_id = config.get("tool_id", "mcp_tool")
        mcp_server_id = config.get("mcp_server_id")
        mcp_tool_name = config.get("mcp_tool_name")
        
        if not mcp_server_id:
            raise ValueError(f"MCP tool '{tool_id}' requires 'mcp_server_id'")
        if not mcp_tool_name:
            raise ValueError(f"MCP tool '{tool_id}' requires 'mcp_tool_name'")
        
        container = get_container()
        server_config = await container.mcp_server_repository.get(mcp_server_id)
        
        if not server_config:
            raise ValueError(f"MCP server '{mcp_server_id}' not found")
        
        parameters = None
        args_schema = config.get("args_schema")
        if args_schema:
            parameters = {}
            for name, schema in args_schema.items():
                if isinstance(schema, CallParameter):
                    parameters[name] = schema
                else:
                    parameters[name] = CallParameter(
                        type=schema.get("type", "string"),
                        description=schema.get("description", ""),
                    )
        
        tool = MCPTool(
            tool_id=tool_id,
            mcp_server_config=server_config,
            mcp_tool_name=mcp_tool_name,
            description=config.get("description"),
            parameters=parameters,
            tags=config.get("tags"),
        )
        
        self.register(tool)
        return tool

    def _create_inline_tool_from_reference(self, ref: ToolReference) -> BaseTool:
        """
        Создает InlineTool из ToolReference.

        Args:
            ref: ToolReference с code

        Returns:
            InlineTool
        """
        if not ref.code:
            raise ValueError(f"ToolReference '{ref.tool_id}' requires 'code' field")

        tool = InlineTool(
            tool_id=ref.tool_id,
            code=ref.code,
            title=ref.title,
            description=ref.description,
            parameters=ref.args_schema,
        )
        
        self.register(tool)
        return tool

    def _create_node_as_tool(self, config: Dict[str, Any]) -> BaseTool:
        """
        Создает NodeAsToolWrapper из inline react_node конфига.
        
        Args:
            config: {
                "tool_id": "my_node",
                "type": "react_node",
                "prompt": "...",
                "tools": [...],
                ...
            }
        
        Returns:
            NodeAsToolWrapper
        """
        # Lazy import to avoid circular dependency
        from apps.agents.src.tools.node_wrapper import NodeAsToolWrapper
        
        return NodeAsToolWrapper(
            node_config=config,
            tool_registry=self
        )