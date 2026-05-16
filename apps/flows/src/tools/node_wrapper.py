"""
NodeAsToolWrapper - обёртка ноды для использования как tool.

Логика:
1. Создает args_schema для LLM из конфига ноды
2. Для llm_node создает изолированный nested_state
3. Вызывает node.execute(state)
4. При FlowInterrupt сохраняет nested_state для resume

Нода сама берет нужные данные через input_mapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, create_model

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.mock import get_mock_for_flow
from apps.flows.src.models import NodeConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.nodes import create_node
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.tools.base import BaseTool, sanitize_tool_name
from core.logging import get_logger
from core.state import ExecutionState, InterruptPathItem

if TYPE_CHECKING:
    from apps.flows.src.runtime.nodes import BaseNode

logger = get_logger(__name__)


def _infer_node_type_for_tool(node: BaseNode) -> str:
    """Тип ноды для NodeConfig: из config или по классу (Zero-Guess)."""
    raw = node.config.get("type") if node.config else None
    if raw:
        return raw if isinstance(raw, str) else str(raw)
    from apps.flows.src.runtime.nodes import (
        ChannelNode,
        CodeNode,
        ExternalAPINode,
        FlowNode,
        LlmNode,
        MCPNode,
        RemoteFlowNode,
        ResourceNode,
    )

    if isinstance(node, LlmNode):
        return NodeType.LLM_NODE.value
    if isinstance(node, CodeNode):
        return NodeType.CODE.value
    if isinstance(node, FlowNode):
        return NodeType.FLOW.value
    if isinstance(node, RemoteFlowNode):
        return NodeType.REMOTE_FLOW.value
    if isinstance(node, ExternalAPINode):
        return NodeType.EXTERNAL_API.value
    if isinstance(node, MCPNode):
        return NodeType.MCP.value
    if isinstance(node, ChannelNode):
        return NodeType.CHANNEL.value
    if isinstance(node, ResourceNode):
        return NodeType.RESOURCE.value
    raise ValueError(
        f"Не удалось определить type ноды для as_tool: {type(node).__name__}, "
        "задайте 'type' в config"
    )


def _build_pydantic_schema(args_schema_dict: dict[str, Any] | None) -> type:
    """Строит Pydantic модель из args_schema для OpenAI tools."""
    if not args_schema_dict:
        return create_model("EmptyArgs")

    fields = {}
    for name, schema in args_schema_dict.items():
        field_type = str
        type_str = schema.get("type", "string")

        if type_str == "integer":
            field_type = int
        elif type_str == "number":
            field_type = float
        elif type_str == "boolean":
            field_type = bool
        elif type_str == "array":
            field_type = list
        elif type_str == "object":
            field_type = dict

        description = schema.get("description", "")
        default = schema.get("default", ...)

        if default is ...:
            fields[name] = (field_type, Field(description=description))
        else:
            fields[name] = (field_type, Field(default=default, description=description))

    return create_model("DynamicArgs", **fields)


class NodeAsToolWrapper(BaseTool):
    """
    Обёртка над любой нодой для использования как tool.

    Поддерживает все типы нод.
    Args записываются в state, нода берет их через input_mapping.
    """

    def __init__(
        self,
        node_config: NodeConfig | dict[str, Any],
        tool_registry: Any | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        if isinstance(node_config, dict):
            self._raw_config = node_config
            node_type = node_config.get("type")
            if not node_type:
                raise ValueError(f"Node config requires 'type' field: {node_config}")
            typed_node_type = node_type if isinstance(node_type, NodeType) else NodeType(str(node_type))
            node_id = node_config.get("tool_id") or node_config.get("node_id")
            if not node_id:
                raise ValueError(f"Node config requires 'tool_id' or 'node_id' field: {node_config}")

            self._args_schema_dict = node_config.get("args_schema")
            if self._args_schema_dict is None and str(node_type) == NodeType.LLM_NODE.value:
                self._args_schema_dict = {
                    "request": {
                        "type": "string",
                        "description": "Запрос к субагенту",
                    },
                }

            self.node_config = NodeConfig(
                node_id=node_id,
                name=node_config.get("name", node_id),
                type=typed_node_type,
                description=str(node_config.get("description") or ""),
                prompt=node_config.get("prompt"),
                tools=node_config.get("tools", []),
                code=node_config.get("code"),
                tags=node_config.get("tags") or [],
            )
        else:
            self._raw_config = None
            self._args_schema_dict = None
            self.node_config = node_config

        self.name = sanitize_tool_name(self.node_config.node_id)
        self.description = self.node_config.description or f"Вызов ноды {self.node_config.name}"
        self.tags = self.node_config.tags or [self.node_config.type]
        self._node: BaseNode | None = None
        self._bound_node: BaseNode | None = None
        self.container = container

        self.args_schema = _build_pydantic_schema(self._args_schema_dict)

    @classmethod
    def from_base_node(
        cls,
        node: BaseNode,
        tool_name: str | None = None,
        tool_description: str | None = None,
    ) -> "NodeAsToolWrapper":
        """
        Один канон с реестром: та же обёртка, что и для inline-нод, с привязкой к уже созданному экземпляру.
        """
        cfg = dict(node.config) if node.config else {}
        node_type = _infer_node_type_for_tool(node)
        merged = {
            **cfg,
            "type": node_type,
            "tool_id": node.node_id,
            "node_id": node.node_id,
            "name": tool_name or cfg.get("name") or node.node_id,
            "description": tool_description
            or cfg.get("description")
            or getattr(node, "description", None)
            or f"Вызов ноды {node.node_id}",
        }
        if not merged.get("args_schema"):
            merged["args_schema"] = {
                "request": {
                    "type": "string",
                    "description": "Запрос к ноде",
                }
            }
        wrapper = cls(merged)
        wrapper._bound_node = node
        wrapper.container = node.container
        wrapper.name = sanitize_tool_name(merged["name"])
        return wrapper

    async def _get_node(self) -> BaseNode:
        """Lazy создание ноды."""
        if self._bound_node is not None:
            return self._bound_node
        if self._node is None:
            if self._raw_config:
                node_dict = dict(self._raw_config)
                node_dict.pop("tool_id", None)
            else:
                tools = []
                if self.node_config.tools:
                    for t in self.node_config.tools:
                        if hasattr(t, "model_dump"):
                            tools.append(t.model_dump())
                        elif isinstance(t, dict):
                            tools.append(t)
                        else:
                            tools.append(t)

                node_dict = {
                    "type": self.node_config.type,
                    "prompt": self.node_config.prompt,
                    "tools": tools,
                    "llm": self.node_config.llm_override.model_dump() if self.node_config.llm_override else {},
                    "code": self.node_config.code,
                    "react": self.node_config.react.model_dump() if self.node_config.react else None,
                }

            self._node = await create_node(
                self.node_config.node_id,
                node_dict,
                container=self.container,
            )

        return self._node

    async def _run_impl(self, args: dict[str, Any], state: ExecutionState) -> Any:
        """
        Вызывает ноду. Для llm_node создает изолированный state и обрабатывает interrupt.
        """
        node_id = self.node_config.node_id
        node_type = self.node_config.type

        mock_result = get_mock_for_flow(state, node_id)
        if mock_result is not None:
            logger.info(f"[wrapper:{node_id}] mock response")
            return mock_result

        node = await self._get_node()
        logger.info(f"[wrapper:{node_id}] run with args: {list(args.keys())}")

        # Для llm_node создаем изолированный state
        if node_type == NodeType.LLM_NODE.value:
            return await self._run_llm_node(node, node_id, args, state)

        # Для остальных нод - простой вызов
        for key, value in args.items():
            setattr(state, key, value)

        result = await node.execute(state)
        return self._extract_response(result)

    async def _run_llm_node(
        self,
        node: BaseNode,
        node_id: str,
        args: dict[str, Any],
        parent_state: ExecutionState
    ) -> Any:
        """
        Выполняет llm_node с изолированным state.
        При interrupt сохраняет nested_state для resume.
        """
        # Проверяем resume: если есть interrupt_path для этой ноды
        is_resume = InterruptManager.is_resume_for_nested(parent_state, node_id)

        if is_resume:
            # Resume: загружаем сохраненный state субагента
            nested_state = InterruptManager.load_nested_state(parent_state, node_id)
            # Передаем ответ пользователя
            nested_state.content = parent_state.content
            # Передаем оставшийся путь interrupt (без первого элемента)
            nested_state.interrupt_path = list(parent_state.interrupt_path[1:])
            content_preview = (parent_state.content or "")[:50]
            logger.info(f"[wrapper:{node_id}] resume with answer='{content_preview}...'")
        else:
            # Первый вызов: создаем новый state для субагента
            nested_state = self._create_nested_state(parent_state, args)

        try:
            result = await node.execute(nested_state)

            # Успешное завершение - копируем результат в родительский state
            self._copy_result_to_parent(nested_state, parent_state)

            # Сохраняем историю субагента
            InterruptManager.save_nested_state(parent_state, node_id, nested_state)

            return self._extract_response(result)

        except FlowInterrupt as e:
            # Сохраняем state субагента для resume
            logger.info(
                f"[wrapper:{node_id}] interrupt, saving nested_state: "
                f"messages={len(nested_state.messages)}"
            )
            InterruptManager.save_nested_state(parent_state, node_id, nested_state)

            # Копируем interrupt_path из субагента в родительский state
            parent_state.interrupt_path = list(nested_state.interrupt_path)

            # Добавляем себя в начало пути
            InterruptManager.push_interrupt_path(
                parent_state,
                InterruptPathItem(
                    type=NodeType.LLM_NODE.value,
                    id=node_id,
                    tool_call=None
                )
            )

            logger.info(f"[wrapper:{node_id}] interrupt: {e.question[:50]}...")
            raise

    def _create_nested_state(
        self, parent_state: ExecutionState, args: dict[str, Any]
    ) -> ExecutionState:
        """Создает изолированный state для субагента."""
        text = args.get("query")
        if text is None:
            text = args.get("content")
        if text is None:
            text = args.get("request")
        if text is None or (isinstance(text, str) and not text.strip()):
            raise ValueError(
                "Аргументы вызова llm_node как tool должны содержать непустой "
                "'query', 'content' или 'request'"
            )

        nested_state = ExecutionState(
            task_id=parent_state.task_id,
            context_id=parent_state.context_id,
            session_id=parent_state.session_id,
            user_id=parent_state.user_id,
            variables=parent_state.variables.copy(),
            content=text if isinstance(text, str) else str(text),
            messages=[],
            branch_id=parent_state.branch_id,
            flow_config_version=parent_state.flow_config_version,
        )

        # Записываем args в nested_state
        for key, value in args.items():
            setattr(nested_state, key, value)

        return nested_state

    def _copy_result_to_parent(
        self, nested_state: ExecutionState, parent_state: ExecutionState
    ) -> None:
        """Копирует результат субагента в родительский state."""
        if nested_state.response:
            parent_state.response = nested_state.response

        parent_state.tool_results.update(nested_state.tool_results)

        # Копируем все extra поля которые субагент записал в state
        extra = nested_state.model_extra
        if extra:
            for key, value in extra.items():
                setattr(parent_state, key, value)

    def _extract_response(self, result: Any) -> Any:
        """Извлекает response из результата."""
        if isinstance(result, ExecutionState):
            if result.response is not None and str(result.response).strip() != "":
                return result.response
            if result.result is not None:
                return result.result
            raise ValueError(
                "Нода завершилась без непустого state.response и без state.result "
                "после вызова как tool"
            )
        if isinstance(result, dict):
            if "response" in result and result["response"] is not None:
                return result["response"]
            if "result" in result:
                return result["result"]
            raise ValueError(
                f"Результат ноды-dict без полей 'response' или 'result': keys={list(result.keys())}"
            )
        if result is None:
            raise ValueError("Результат вызова ноды как tool — None")
        return result

    def __repr__(self) -> str:
        return f"NodeAsToolWrapper({self.node_config.node_id})"
