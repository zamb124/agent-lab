"""
ToolRegistry - реестр инструментов.

Zero-Guess Architecture:
- Единственная точка создания и получения tools
- Все tools регистрируются явно
- Нет ToolFactory - логика перенесена сюда
"""

import importlib
from typing import Any

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.eval.inline_tool_sanitize import strip_forbidden_platform_import_lines
from apps.flows.src.models import ToolReference
from apps.flows.src.models.enums import CodeMode, NodeType, ReactToolRole
from apps.flows.src.models.mcp import MCPServerConfig
from apps.flows.src.models.tool_reference import CallParameter
from apps.flows.src.tools.base import BaseTool, CodeTool
from apps.flows.src.tools.json_schema_parameters import resolve_tool_parameters_schema
from apps.flows.src.tools.mcp_wrapper import MCPTool
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.logging import get_logger

logger = get_logger(__name__)

# Тулы, чей исходник кладётся в tool_repository для документации/шаблона, но исполнять
# их как CodeTool нельзя: тело опирается на модули вне sandbox (импорты режутся).
_TOOL_IDS_PROCESS_BUILTIN_ONLY = frozenset({"sandbox_codegen"})


def _browser_runtime_mcp_tool_parameters_schema(
    server_config: MCPServerConfig,
    mcp_tool_name: str,
) -> dict[str, Any] | None:
    """
    JSON Schema аргументов MCP tools Browser Runtime для подсказки LLM.

    Применяется только если URL MCP указывает на HTTP-эндпоинт browser-сервиса.
    """
    if "/browser/" not in (server_config.url or ""):
        return None
    try:
        from apps.browser.api.mcp import (
            ToolCloseSessionArgs,
            ToolCreateSessionArgs,
            ToolNavigateArgs,
            ToolObserveArgs,
        )
    except ImportError:
        return None

    model_by_name: dict[str, Any] = {
        "browser_create_session": ToolCreateSessionArgs,
        "browser_navigate": ToolNavigateArgs,
        "browser_observe": ToolObserveArgs,
        "browser_close_session": ToolCloseSessionArgs,
    }
    model = model_by_name.get(mcp_tool_name)
    if model is None:
        return None
    schema = model.model_json_schema()
    schema.pop("title", None)
    if mcp_tool_name == "browser_navigate":
        wp = schema.get("properties", {}).get("wait_policy")
        if isinstance(wp, dict):
            wp["description"] = (
                "Строка: domcontentloaded, networkidle либо selector:<css>. "
                "Не используй load и не передавай объект {\"event\": ...}."
            )
    return schema


class ToolRegistry:
    """
    Реестр инструментов.

    Единая точка для:
    - Регистрации builtin tools
    - Создания тулов из конфигов с полем code
    - Создания node-as-tool wrappers
    - Получения tools по имени
    """

    def __init__(self, *, container: FlowRuntimeContainer | None = None):
        self._tools: dict[str, BaseTool] = {}
        self._initialized = False
        self.container = container

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

        builtin_tools = [
            getattr(importlib.import_module(module_name), attr_name)
            for module_name, attr_name in BUILTIN_TOOL_SPECS
        ]

        for tool in builtin_tools:
            self.register(tool)

        self._initialized = True
        logger.info(f"Зарегистрировано {len(builtin_tools)} встроенных tools")

    # =========================================================================
    # Методы создания tools
    # =========================================================================

    async def materialize(self, tool_ref: dict[str, Any] | ToolReference) -> BaseTool:
        """
        Единая материализация runnable tool.

        Исполнение только через код в конфиге (CodeTool / нода как tool). Записи в
        ``tool_repository`` — шаблоны с полем ``code``; процессный ``registry.get`` (FunctionTool)
        для runtime flow не используется.

        Порядок веток:
        1. ``code_mode=mcp_tool`` → MCPTool
        2. ``tool_id`` без инлайн ``code`` → если есть процессный builtin (``register_builtin_tools``), он имеет приоритет над шаблоном в ``tool_repository`` (Python-реализация, не sandbox).
        3. иначе ``tool_id`` без ``code``/``prompt`` (не ``mcp:``), тип не нода-as-tool → merge из ``tool_repository``
        4. Поле ``type`` (flow / llm_node / …) или ``prompt`` → NodeAsToolWrapper
        5. Непустой ``code`` → CodeTool, кроме ``tool_id`` из
           ``_TOOL_IDS_PROCESS_BUILTIN_ONLY`` (процессный FunctionTool).
        6. ``type=code`` без кода → NodeAsToolWrapper
        7. иначе ValueError
        """
        if isinstance(tool_ref, ToolReference):
            ref: dict[str, Any] = tool_ref.model_dump(exclude_none=True)
        elif isinstance(tool_ref, dict):
            ref = dict(tool_ref)
        else:
            raise ValueError(f"Tool ref must be dict or ToolReference, got {type(tool_ref)}")

        code_mode = ref.get("code_mode")
        if code_mode == CodeMode.MCP_TOOL.value or code_mode == CodeMode.MCP_TOOL:
            return await self._create_mcp_tool(ref)

        def _has_nonempty_inline_code(r: dict[str, Any]) -> bool:
            c = r.get("code")
            return isinstance(c, str) and bool(c.strip())

        def _tool_lookup_id(r: dict[str, Any]) -> str | None:
            raw = r.get("tool_id") or r.get("name")
            return raw if isinstance(raw, str) and raw else None

        node_exec_kind = ref.get("type")
        _node_as_tool_kind = node_exec_kind in (
            NodeType.LLM_NODE.value,
            NodeType.FLOW.value,
            NodeType.REMOTE_FLOW.value,
            NodeType.EXTERNAL_API.value,
            NodeType.MCP.value,
            NodeType.CHANNEL.value,
            NodeType.HITL_NODE.value,
            "channel",
        )

        tid = _tool_lookup_id(ref)
        if (
            tid
            and not _has_nonempty_inline_code(ref)
            and not ref.get("prompt")
            and not tid.startswith("mcp:")
            and not _node_as_tool_kind
        ):
            if not self._initialized:
                self.register_builtin_tools()
            builtin_tool = self.get(tid)
            if builtin_tool is not None:
                return builtin_tool

            container = self.container
            if container is None:
                raise RuntimeError(f"Tool '{tid}' requires FlowContainer to load tool template")
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

        if node_exec_kind in (
            NodeType.LLM_NODE.value,
            NodeType.FLOW.value,
            NodeType.REMOTE_FLOW.value,
            NodeType.EXTERNAL_API.value,
            NodeType.MCP.value,
            NodeType.CHANNEL.value,
            NodeType.HITL_NODE.value,
            "channel",
        ) or ref.get("prompt"):
            return self._create_node_as_tool(ref)

        if _has_nonempty_inline_code(ref):
            tid_builtin = _tool_lookup_id(ref)
            if tid_builtin and tid_builtin in _TOOL_IDS_PROCESS_BUILTIN_ONLY:
                if not self._initialized:
                    self.register_builtin_tools()
                process_tool = self.get(tid_builtin)
                if process_tool is None:
                    raise ValueError(
                        f"Tool '{tid_builtin}': требуется процессный builtin (register_builtin_tools)"
                    )
                return process_tool
            code_text = ref["code"]
            if not isinstance(code_text, str):
                raise ValueError(f"Tool 'code' must be str, got {type(code_text)}")
            return self._create_code_tool_from_config(ref)

        if node_exec_kind == NodeType.CODE.value:
            return self._create_node_as_tool(ref)

        raise ValueError(f"Tool config requires 'type' or 'code' field: {ref}")

    async def create_tool(self, tool_ref: str | dict[str, Any] | ToolReference) -> BaseTool:
        """Алиас на ``materialize``; строки запрещены (инлайн через FlowsLoader)."""
        if isinstance(tool_ref, str):
            raise ValueError(
                f"Tool '{tool_ref}' passed as string. All tools must be inline with code. "
                f"Flow must be assembled with FlowsLoader which inlines all tools."
            )
        return await self.materialize(tool_ref)

    async def create_tools(
        self, tool_refs: list[str | dict[str, Any] | ToolReference]
    ) -> list[BaseTool]:
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
                    f"Flow must be assembled with FlowsLoader which inlines all tools."
                )
            if isinstance(ref, ToolReference):
                ref = ref.model_dump(exclude_none=True)
            if not isinstance(ref, dict):
                raise ValueError(f"Unknown tool ref type: {type(ref)}")
            tools.append(await self.materialize(ref))

        return tools

    def _create_code_tool_from_config(self, config: dict[str, Any]) -> BaseTool:
        """
        Создает CodeTool из dict-конфига (поле code).

        Args:
            config: {
                "tool_id": "my_tool",
                "description": "...",
                "args_schema": {"param": {"type": "string", "description": "..."}},
                "code": "def execute(args, state): ..."
            }

        Returns:
            CodeTool (только для списка ноды; в глобальный реестр не кладём, иначе
            тулы с тем же именем затеняют встроенные FunctionTool между тестами/flow).
        """
        tool_id = config.get("tool_id", "code_tool")
        code = config.get("code")
        if not code:
            raise ValueError(f"Code tool '{tool_id}' requires 'code' field")
        code = strip_forbidden_platform_import_lines(code)

        parameters_cp: dict[str, CallParameter] | None = None
        args_schema = config.get("args_schema")
        if args_schema:
            parameters_cp = {}
            for name, schema in args_schema.items():
                if isinstance(schema, CallParameter):
                    parameters_cp[name] = schema
                else:
                    parameters_cp[name] = CallParameter(
                        type=schema.get("type", "string"),
                        description=schema.get("description", ""),
                        required=schema.get("required", True),
                    )

        ps_raw = config.get("parameters_schema")
        resolved_schema: dict[str, Any] | None = None
        if ps_raw and isinstance(ps_raw, dict) and ps_raw.get("type") == "object":
            resolved_schema = ps_raw
        elif parameters_cp:
            resolved_schema = resolve_tool_parameters_schema(
                parameters_schema=None,
                args_schema=parameters_cp,
            )

        rr_raw = config.get("react_role", ReactToolRole.STANDARD.value)
        react_role = (
            ReactToolRole(rr_raw) if isinstance(rr_raw, str) else rr_raw
        )
        if not isinstance(react_role, ReactToolRole):
            react_role = ReactToolRole.STANDARD

        resources = config.get("resources")

        tool = CodeTool(
            tool_id=tool_id,
            code=code,
            title=config.get("title"),
            description=config.get("description"),
            parameters_schema=resolved_schema,
            react_role=react_role,
            resources=resources,
            container=self.container,
        )
        return tool

    async def _create_mcp_tool(self, config: dict[str, Any]) -> BaseTool:
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
        tool_id = config.get("tool_id", "mcp_tool")
        mcp_server_id = config.get("mcp_server_id")
        mcp_tool_name = config.get("mcp_tool_name")

        if not mcp_server_id:
            raise ValueError(f"MCP tool '{tool_id}' requires 'mcp_server_id'")
        if not mcp_tool_name:
            raise ValueError(f"MCP tool '{tool_id}' requires 'mcp_tool_name'")
        if self.container is None:
            raise RuntimeError("ToolRegistry requires FlowContainer for MCP tools")

        server_config = await self.container.mcp_server_repository.get(mcp_server_id)

        if not server_config:
            raise ValueError(f"MCP server '{mcp_server_id}' not found")

        parameters_schema: dict[str, Any] | None = None
        ps_raw = config.get("parameters_schema")
        if isinstance(ps_raw, dict) and ps_raw.get("type") == "object":
            parameters_schema = ps_raw
        if parameters_schema is None:
            parameters_schema = _browser_runtime_mcp_tool_parameters_schema(
                server_config, mcp_tool_name
            )

        parameters: dict[str, CallParameter] | None = None
        args_schema = config.get("args_schema")
        if args_schema and parameters_schema is None:
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
            parameters_schema=parameters_schema,
            tags=config.get("tags"),
        )

        self.register(tool)
        return tool

    def _create_node_as_tool(self, config: dict[str, Any]) -> BaseTool:
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
            tool_registry=self,
            container=self.container,
        )
