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
from typing import Protocol, TypeAlias, cast

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import NodeConfig, ToolReference
from apps.flows.src.models.enums import CodeMode, NodeType
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.code_tool import CodeTool
from apps.flows.src.tools.mcp_wrapper import MCPTool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS, builtin_tool_ids
from core.capabilities.source_sanitize import strip_forbidden_platform_import_lines
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


ToolMaterializeInput: TypeAlias = ToolReference | NodeConfig | JsonObject


class NodeToolWrapperFactory(Protocol):
    def __call__(
        self,
        node_config: NodeConfig,
        *,
        container: FlowRuntimeContainer | None = None,
    ) -> BaseTool: ...


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
        container: FlowRuntimeContainer | None = None,
        node_tool_wrapper_cls: NodeToolWrapperFactory | None = None,
    ):
        self._tools: dict[str, BaseTool] = {}
        self._initialized: bool = False
        self.container: FlowRuntimeContainer | None = container
        self._node_tool_wrapper_cls: NodeToolWrapperFactory | None = node_tool_wrapper_cls

    def register(self, tool: BaseTool) -> None:
        """Регистрирует tool в процессном реестре (builtin, MCPTool и т.д.)."""
        if isinstance(tool, CodeTool):
            raise ValueError(
                "CodeTool не регистрируется в ToolRegistry: только materialize → список tools ноды."
            )
        self._tools[tool.name] = tool
        logger.debug(f"Tool зарегистрирован: {tool.name}")

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
            self.register(tool)

        self._initialized = True
        logger.info(f"Зарегистрировано {len(builtin_tools)} встроенных tools")

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
            NodeType.EXTERNAL_API,
            NodeType.MCP,
            NodeType.CHANNEL,
            NodeType.HITL_NODE,
        }:
            return True
        prompt = config.get("prompt")
        return isinstance(prompt, str) and bool(prompt.strip())

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
        2. ``tool_id`` без ``code``/``prompt`` (не ``mcp:``), тип не нода-as-tool → template из ``tool_repository``
        3. Поле ``type`` (flow / llm_node / …) или ``prompt`` → NodeAsToolWrapper
        4. Непустой ``code`` → CodeTool.
        5. ``tool_id`` из builtin ids без DB/inline code → процессный FunctionTool
        6. ``type=code`` без кода → NodeAsToolWrapper
        7. иначе ValueError
        """
        if isinstance(tool_ref, NodeConfig):
            return self._create_node_as_tool(tool_ref)

        if isinstance(tool_ref, dict):
            raw_code_mode = tool_ref.get("code_mode")
            if raw_code_mode == CodeMode.MCP_TOOL.value:
                return await self._create_mcp_tool(ToolReference.model_validate(tool_ref))
            if self._is_node_as_tool_payload(tool_ref):
                return self._create_node_as_tool(NodeConfig.model_validate(tool_ref))

        ref = (
            tool_ref
            if isinstance(tool_ref, ToolReference)
            else ToolReference.model_validate(tool_ref)
        )

        if ref.code_mode == CodeMode.MCP_TOOL:
            return await self._create_mcp_tool(ref)

        tid = ref.tool_id
        has_inline_code = bool(ref.code and ref.code.strip())

        if tid and not has_inline_code and not tid.startswith("mcp:"):
            container = self.container
            if container is None:
                raise RuntimeError(f"Tool '{tid}' requires FlowContainer to load tool template")
            stored = await container.tool_repository.get(tid)
            if stored is None:
                raise ValueError(
                    f"Tool '{tid}': нет inline code в конфиге и нет шаблона в tool_repository"
                )
            stored_payload = cast(JsonObject, stored.model_dump(mode="json", exclude_none=True))
            override_payload = cast(
                JsonObject,
                ref.model_dump(mode="json", exclude_unset=True, exclude_none=True),
            )
            ref = ToolReference.model_validate({**stored_payload, **override_payload})
            has_inline_code = bool(ref.code and ref.code.strip())
            if not has_inline_code:
                raise ValueError(f"Tool '{tid}': шаблон в tool_repository без непустого поля code")

        if has_inline_code:
            return self._create_code_tool_from_config(ref)

        if tid and tid in builtin_tool_ids():
            if not self._initialized:
                self.register_builtin_tools()
            builtin_tool = self.get(tid)
            if builtin_tool is None:
                raise ValueError(f"Builtin platform tool '{tid}' is not registered")
            return builtin_tool

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

        Args:
            tool_refs: Список dict-конфигов или ToolReference

        Returns:
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

        Args:
            config: {
                "tool_id": "my_tool",
                "description": "...",
                "parameters_schema": {"type": "object", "properties": {...}, "required": [...]},
                "code": "def run(args, state): ..."
            }

        Returns:
            CodeTool (только для списка ноды; в глобальный реестр не кладём, иначе
            тулы с тем же именем затеняют встроенные FunctionTool между тестами/flow).
        """
        tool_id = config.tool_id
        code = config.code
        if not code:
            raise ValueError(f"Code tool '{tool_id}' requires 'code' field")
        code = strip_forbidden_platform_import_lines(code)

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
            container=self.container,
        )
        return tool

    async def _create_mcp_tool(self, config: ToolReference) -> BaseTool:
        """
        Создает MCPTool из конфига.

        Args:
            config: {
                "tool_id": "mcp:server:tool",
                "description": "...",
                "parameters_schema": {"type": "object", "properties": {...}, "required": [...]},
                "mcp_server_id": "server_id",
                "mcp_tool_name": "tool_name"
            }

        Returns:
            MCPTool
        """
        tool_id = config.tool_id
        mcp_contract = config.require_mcp_contract()

        if self.container is None:
            raise RuntimeError("ToolRegistry requires FlowContainer for MCP tools")

        server_config = await self.container.mcp_server_repository.get(mcp_contract.server_id)

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

    def _create_node_as_tool(self, config: NodeConfig) -> BaseTool:
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
        if self._node_tool_wrapper_cls is None:
            raise RuntimeError(
                "ToolRegistry requires node_tool_wrapper_cls for node-as-tool configs"
            )

        return self._node_tool_wrapper_cls(
            node_config=config,
            container=self.container,
        )
