"""
ToolRegistry - реестр инструментов.

Zero-Guess Architecture:
- Единственная точка создания и получения tools
- Все tools регистрируются явно
- Нет ToolFactory - логика перенесена сюда
"""

from typing import Any, Dict, List, Optional, Union

from core.logging import get_logger
from apps.flows.src.models import ToolReference
from apps.flows.src.models.enums import CodeMode, NodeType
from apps.flows.src.models.tool_reference import CallParameter
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.base import BaseTool, InlineTool
from apps.flows.src.tools.mcp_wrapper import MCPTool

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

        from apps.flows.tools import (
            calculator,
            final_answer,
            finish,
            read_file,
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
            read_file,
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

    async def materialize(self, tool_ref: Union[Dict[str, Any], ToolReference]) -> BaseTool:
        """
        Единая материализация runnable tool.

        Исполнение только через инлайн-код (InlineTool / нода как tool). Записи в
        ``tool_repository`` — шаблоны с полем ``code``; процессный ``registry.get`` (FunctionTool)
        для runtime flow не используется.

        Порядок веток:
        1. ``code_mode=mcp_tool`` → MCPTool
        2. ``tool_id`` без ``code``/``prompt`` (не ``mcp:``) → merge из ``tool_repository``; без шаблона или без ``code`` → ValueError
        3. Поле ``type`` из NodeType / ``channel`` или наличие ``prompt`` → NodeAsToolWrapper
        4. Непустой ``code`` → InlineTool
        5. ``type=code`` без кода → NodeAsToolWrapper
        6. иначе ValueError
        """
        if isinstance(tool_ref, ToolReference):
            ref: Dict[str, Any] = tool_ref.model_dump(exclude_none=True)
        elif isinstance(tool_ref, dict):
            ref = dict(tool_ref)
        else:
            raise ValueError(f"Tool ref must be dict or ToolReference, got {type(tool_ref)}")

        code_mode = ref.get("code_mode")
        if code_mode == CodeMode.MCP_TOOL.value or code_mode == CodeMode.MCP_TOOL:
            return await self._create_mcp_tool(ref)

        def _has_nonempty_inline_code(r: Dict[str, Any]) -> bool:
            c = r.get("code")
            return isinstance(c, str) and bool(c.strip())

        def _tool_lookup_id(r: Dict[str, Any]) -> Optional[str]:
            raw = r.get("tool_id") or r.get("name")
            return raw if isinstance(raw, str) and raw else None

        tid = _tool_lookup_id(ref)
        if (
            tid
            and not _has_nonempty_inline_code(ref)
            and not ref.get("prompt")
            and not tid.startswith("mcp:")
        ):
            from apps.flows.src.container import get_container

            container = get_container()
            stored = await container.tool_repository.get(tid)
            if stored is None:
                raise ValueError(
                    f"Tool '{tid}': нет inline code в конфиге и нет шаблона в tool_repository"
                )
            ref = {**stored.model_dump(exclude_none=True), **ref}
            if not _has_nonempty_inline_code(ref):
                raise ValueError(
                    f"Tool '{tid}': шаблон в tool_repository без непустого поля code"
                )
            tid = _tool_lookup_id(ref)

        node_exec_kind = ref.get("type")

        if node_exec_kind in (
            NodeType.LLM_NODE.value,
            NodeType.FLOW.value,
            NodeType.REMOTE_FLOW.value,
            NodeType.EXTERNAL_API.value,
            NodeType.MCP.value,
            NodeType.CHANNEL.value,
            "channel",
        ) or ref.get("prompt"):
            return self._create_node_as_tool(ref)

        if _has_nonempty_inline_code(ref):
            code_text = ref["code"]
            if not isinstance(code_text, str):
                raise ValueError(f"Tool 'code' must be str, got {type(code_text)}")
            return self._create_inline_tool_from_config(ref)

        if node_exec_kind == NodeType.CODE.value:
            return self._create_node_as_tool(ref)

        raise ValueError(f"Tool config requires 'type' or 'code' field: {ref}")

    async def create_tool(self, tool_ref: Union[str, Dict[str, Any], ToolReference]) -> BaseTool:
        """Алиас на ``materialize``; строки запрещены (инлайн через FlowsLoader)."""
        if isinstance(tool_ref, str):
            raise ValueError(
                f"Tool '{tool_ref}' passed as string. All tools must be inline with code. "
                f"Flow must be assembled with FlowsLoader which inlines all tools."
            )
        return await self.materialize(tool_ref)

    async def create_tools(
        self, tool_refs: List[Union[str, Dict[str, Any], ToolReference]]
    ) -> List[BaseTool]:
        """
        Создает список tools из inline конфигов (только InlineTool / нода как tool).

        Args:
            tool_refs: Список dict-конфигов или ToolReference

        Returns:
            Список BaseTool
        """
        tools: List[BaseTool] = []

        for ref in tool_refs:
            if isinstance(ref, str):
                raise ValueError(
                    f"Tool '{ref}' passed as string. All tools must be inline with code. "
                    f"Flow must be assembled with FlowsLoader which inlines all tools."
                )
            if isinstance(ref, ToolReference):
                ref = ref.model_dump(exclude_none=True)
            if not isinstance(ref, dict):
                raise ValueError(f"Unknown tool ref type: {type(ref)}")
            tools.append(await self.materialize(ref))

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
            InlineTool (только для списка ноды; в глобальный реестр не кладём, иначе
            инлайн с тем же именем затеняет встроенные FunctionTool между тестами/flow).
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

        rr_raw = config.get("react_role", ReactToolRole.STANDARD.value)
        react_role = (
            ReactToolRole(rr_raw) if isinstance(rr_raw, str) else rr_raw
        )
        if not isinstance(react_role, ReactToolRole):
            react_role = ReactToolRole.STANDARD

        resources = config.get("resources")

        tool = InlineTool(
            tool_id=tool_id,
            code=code,
            title=config.get("title"),
            description=config.get("description"),
            parameters=parameters,
            react_role=react_role,
            resources=resources,
        )
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
        from apps.flows.src.container import get_container
        
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

    def _create_node_as_tool(self, config: Dict[str, Any]) -> BaseTool:
        """
        Создает NodeAsToolWrapper из inline llm_node конфига.
        
        Args:
            config: {
                "tool_id": "my_node",
                "type": "llm_node",
                "prompt": "...",
                "tools": [...],
                ...
            }
        
        Returns:
            NodeAsToolWrapper
        """
        # Lazy import to avoid circular dependency
        from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper
        
        return NodeAsToolWrapper(
            node_config=config,
            tool_registry=self
        )