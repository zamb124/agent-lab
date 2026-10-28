"""
ToolRegistry - реестр инструментов.

Zero-Guess Architecture:
- Единственная точка создания и получения tools
- Все tools регистрируются явно
- Нет ToolFactory - логика перенесена сюда
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence

from apps.flows.src.contracts import FlowFactoryProtocol
from apps.flows.src.models import FlowToolReference, MCPServerConfig, NodeConfig, ToolReference
from apps.flows.src.models.enums import CodeMode, NodeType
from apps.flows.src.runtime.nodes import NodeConstructor
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.builtin_dependencies import BuiltinToolClient
from apps.flows.src.tools.code_tool import CodeTool
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.src.tools.materialize import ToolMaterializeInput
from apps.flows.src.tools.mcp_wrapper import MCPTool
from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS, builtin_tool_ids
from core.capabilities.source_sanitize import reject_forbidden_platform_imports
from core.logging import get_logger
from core.types import JsonObject, model_json_object

logger = get_logger(__name__)


class ToolRegistry:
    """
    Реестр инструментов.

    Единая точка для:
    - Регистрации builtin tools
    - Создания тулов из конфигов с полем code
    - Создания node-as-tool wrappers
    - Получения tools по имени
    """

    def __init__(
        self,
        *,
        clients: tuple[BuiltinToolClient, ...] = (),
        node_constructor: NodeConstructor | None = None,
        flow_factory: FlowFactoryProtocol,
    ):
        self._tools: dict[str, BaseTool] = {}
        self._initialized: bool = False
        self._clients: tuple[BuiltinToolClient, ...] = clients
        self._node_constructor: NodeConstructor | None = node_constructor
        self._flow_factory: FlowFactoryProtocol = flow_factory

    def register(self, tool: BaseTool) -> None:
        """Регистрирует tool в процессном реестре (builtin, MCPTool и т.д.)."""
        if isinstance(tool, CodeTool):
            raise ValueError(
                "CodeTool is not registered in ToolRegistry: materialize only → node tools list."
            )
        self._tools[tool.name] = tool
        logger.debug("flows.tool.registered", tool_name=tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Получает tool по имени."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Проверяет зарегистрирован ли tool."""
        return name in self._tools

    def list_all(self) -> dict[str, BaseTool]:
        """Возвращает все зарегистрированные tools."""
        return dict(self._tools)

    def register_builtin_tools(self) -> None:
        """Регистрирует встроенные tools."""
        if self._initialized:
            return

        builtin_tools: list[BaseTool] = []
        for module_name, attr_name in BUILTIN_TOOL_SPECS:
            module = importlib.import_module(module_name)
            raw_tool = module.__dict__.get(attr_name)
            if not isinstance(raw_tool, BaseTool):
                raise TypeError(
                    f"Builtin tool {module_name}.{attr_name} must be a BaseTool instance"
                )
            builtin_tools.append(raw_tool)

        for tool in builtin_tools:
            registered = (
                tool.with_dependencies(self._clients)
                if isinstance(tool, FunctionTool) and self._clients
                else tool
            )
            self.register(registered)

        self._initialized = True
        logger.info("flows.tool.builtins_registered", count=len(builtin_tools))

    @staticmethod
    def _is_node_as_tool_payload(config: JsonObject) -> bool:
        raw_type = config.get("type")
        node_type: NodeType | None = None
        if isinstance(raw_type, str) and raw_type:
            try:
                node_type = NodeType(raw_type)
            except ValueError:
                node_type = None
        if node_type in {
            NodeType.LLM_NODE,
            NodeType.FLOW,
            NodeType.REMOTE_FLOW,
            NodeType.CODE_AGENT,
            NodeType.EXTERNAL_API,
            NodeType.MCP,
            NodeType.DATASOURCE,
            NodeType.CHANNEL,
            NodeType.HITL_NODE,
        }:
            return True
        prompt = config.get("prompt")
        return isinstance(prompt, str) and bool(prompt.strip())

    @staticmethod
    def _is_generated_platform_tool_template(config: ToolReference) -> bool:
        code = config.code
        if code is None:
            return False
        source = code.lstrip()
        return source.startswith(f"# platform:builtin:{config.tool_id}") or source.startswith(
            f"# platform:tool-capability:{config.tool_id}"
        )

    def _registered_builtin_tool(self, tool_id: str) -> BaseTool:
        if not self._initialized:
            self.register_builtin_tools()
        builtin_tool = self.get(tool_id)
        if builtin_tool is None:
            raise ValueError(f"Builtin platform tool '{tool_id}' is not registered")
        return builtin_tool

    # =========================================================================
    # Методы создания tools
    # =========================================================================

    async def materialize(self, tool_ref: ToolMaterializeInput) -> BaseTool:
        """
        Единая материализация runnable tool.

        Исполнение кода идёт через CodeTool/remote runner, если в ref или
        tool_repository есть непустое поле ``code``. Builtin ids из
        ``BUILTIN_TOOL_SPECS`` — bootstrap seed для загрузки в БД.

        Порядок веток:
        1. ``code_mode=mcp_tool`` → MCPTool
        2. ``tool_id`` из builtin ids без inline source или со сгенерированным platform-шаблоном → зарегистрированный platform tool
        3. ``tool_id`` без ``code``/``prompt`` (не ``mcp:``), тип не нода-as-tool → template из ``tool_repository``
        4. Поле ``type`` (flow / llm_node / …) или ``prompt`` → NodeAsToolWrapper
        5. Непустой ``code`` → CodeTool.
        6. иначе ValueError
        """
        if isinstance(tool_ref, NodeConfig):
            return await self._create_node_as_tool(tool_ref)
        if isinstance(tool_ref, FlowToolReference):
            return await self._create_node_as_tool(
                NodeConfig.model_validate(tool_ref.model_dump(mode="python"))
            )

        if isinstance(tool_ref, dict):
            raw_code_mode = tool_ref.get("code_mode")
            if raw_code_mode == CodeMode.MCP_TOOL.value:
                return await self._create_mcp_tool(ToolReference.model_validate(tool_ref))
            if tool_ref.get("type") == NodeType.FLOW.value:
                flow_ref = FlowToolReference.model_validate(tool_ref)
                return await self._create_node_as_tool(
                    NodeConfig.model_validate(flow_ref.model_dump(mode="python"))
                )
            if self._is_node_as_tool_payload(tool_ref):
                return await self._create_node_as_tool(NodeConfig.model_validate(tool_ref))

        ref = (
            tool_ref
            if isinstance(tool_ref, ToolReference)
            else ToolReference.model_validate(tool_ref)
        )

        if ref.code_mode == CodeMode.MCP_TOOL:
            return await self._create_mcp_tool(ref)

        tid = ref.tool_id
        has_inline_code = bool(ref.code and ref.code.strip())

        if tid and tid in builtin_tool_ids() and (
            not has_inline_code or self._is_generated_platform_tool_template(ref)
        ):
            return self._registered_builtin_tool(tid)

        if tid and not has_inline_code and not tid.startswith("mcp:"):
            stored = await ToolReference.get(ToolReference.row_id_for_active_company(tid))
            if stored is None:
                raise ValueError(
                    f"Tool '{tid}': no inline code in config and no template in tool_repository"
                )
            stored_payload = model_json_object(stored, "ToolReference", exclude_none=True)
            override_payload = model_json_object(
                ref,
                "ToolReference",
                exclude_unset=True,
                exclude_none=True,
            )
            ref = ToolReference.model_validate({**stored_payload, **override_payload})
            has_inline_code = bool(ref.code and ref.code.strip())
            if not has_inline_code:
                raise ValueError(f"Tool '{tid}': tool_repository template has no non-empty code field")

        if has_inline_code:
            return self._create_code_tool_from_config(ref)

        raise ValueError(f"Tool config requires 'type' or 'code' field: {ref.tool_id}")

    async def create_tool(self, tool_ref: str | ToolMaterializeInput) -> BaseTool:
        """Алиас на ``materialize``; строки запрещены (инлайн через FlowsLoader)."""
        if isinstance(tool_ref, str):
            raise ValueError(
                f"Tool '{tool_ref}' passed as string. All tools must be inline with code. "
                + "Flow must be assembled with FlowsLoader which inlines all tools."
            )
        return await self.materialize(tool_ref)

    async def create_tools(self, tool_refs: Sequence[str | ToolMaterializeInput]) -> list[BaseTool]:
        """
        Создает список tools из конфигов (CodeTool / нода как tool).

        Аргументы:
            tool_refs: Список dict-конфигов или ToolReference

        Возвращает:
            Список BaseTool
        """
        tools: list[BaseTool] = []

        for ref in tool_refs:
            if isinstance(ref, str):
                raise ValueError(
                    f"Tool '{ref}' passed as string. All tools must be inline with code. "
                    + "Flow must be assembled with FlowsLoader which inlines all tools."
                )
            tools.append(await self.materialize(ref))

        return tools

    def _create_code_tool_from_config(self, config: ToolReference) -> BaseTool:
        """
        Создает CodeTool из dict-конфига (поле code).

        Аргументы:
            config: {
                "tool_id": "my_tool",
                "description": "...",
                "parameters_schema": {"type": "object", "properties": {...}, "required": [...]},
                "code": "def run(args, state): ..."
            }

        Возвращает:
            CodeTool (только для списка ноды; в глобальный реестр не кладём, иначе
            тулы с тем же именем затеняют встроенные FunctionTool между тестами/flow).
        """
        tool_id = config.tool_id
        code = config.code
        if not code:
            raise ValueError(f"Code tool '{tool_id}' requires 'code' field")
        code = reject_forbidden_platform_imports(code)

        tool = CodeTool(
            tool_id=tool_id,
            code=code,
            title=config.title,
            description=config.description,
            parameters_schema=config.effective_parameters_schema(),
            permission=config.permission,
            react_role=config.react_role,
            language=config.language,
            entrypoint=config.entrypoint,
            resources=config.resources,
        )
        return tool

    async def _create_mcp_tool(self, config: ToolReference) -> BaseTool:
        """
        Создает MCPTool из конфига.

        Аргументы:
            config: {
                "tool_id": "mcp:server:tool",
                "description": "...",
                "parameters_schema": {"type": "object", "properties": {...}, "required": [...]},
                "mcp_server_id": "server_id",
                "mcp_tool_name": "tool_name"
            }

        Возвращает:
            MCPTool
        """
        tool_id = config.tool_id
        mcp_contract = config.require_mcp_contract()

        server_config = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(mcp_contract.server_id))

        if not server_config:
            raise ValueError(f"MCP server '{mcp_contract.server_id}' not found")

        tool = MCPTool(
            tool_id=tool_id,
            mcp_server_config=server_config,
            mcp_tool_name=mcp_contract.tool_name,
            description=config.description,
            parameters_schema=mcp_contract.parameters_schema,
            mcp_schema_hash=mcp_contract.schema_hash,
            mcp_schema_version=mcp_contract.schema_version,
            tags=config.tags,
        )

        self.register(tool)
        return tool

    async def _create_node_as_tool(self, config: NodeConfig) -> BaseTool:
        """Собирает ноду и отдаёт обёртку, привязанную к этому экземпляру."""
        constructor = self._node_constructor
        if constructor is None:
            raise RuntimeError(f"Node tool '{config.node_id}' requires a node constructor")
        node_dict = model_json_object(config, "NodeConfig", exclude_none=True)
        _ = node_dict.pop("tool_id", None)
        node = constructor.materialize(
            config.node_id,
            node_dict,
            tool_registry=self,
            flow_factory=self._flow_factory,
        )
        wrapper = NodeAsToolWrapper(node_config=config, call_type=config.call_type)
        wrapper.bind_node(node)
        return wrapper
