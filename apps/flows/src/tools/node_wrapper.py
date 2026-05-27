"""
NodeAsToolWrapper - обёртка ноды для использования как tool.

Логика:
1. Отдает JSON Schema аргументов для LLM из NodeConfig
2. Для llm_node создает изолированный nested_state
3. Вызывает node.execute(state)
4. При FlowInterrupt сохраняет nested_state для resume

Нода сама берет нужные данные через input_mapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast, override

from apps.flows.src.container_contracts import FlowRuntimeContainer, as_flow_runtime_container
from apps.flows.src.durable_execution import (
    NodeCompletedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    SuperstepStartedPayload,
    WorkflowEventType,
    build_state_delta,
)
from apps.flows.src.models import NodeConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.nodes import (
    ChannelNode,
    CodeNode,
    ExternalAPINode,
    FlowNode,
    LlmNode,
    MCPNode,
    RemoteFlowNode,
    ResourceNode,
    create_node,
)
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.tools.base import (
    BaseTool,
    ToolArguments,
    ToolContainerRef,
    ToolParametersSchema,
    ToolResult,
    sanitize_tool_name,
)
from core.logging import get_logger
from core.state import ExecutionState, InterruptPathItem
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

if TYPE_CHECKING:
    from apps.flows.src.runtime.nodes import BaseNode

logger = get_logger(__name__)


def _infer_node_type_for_tool(node: BaseNode) -> NodeType:
    """Тип ноды для NodeConfig: из config или по классу (Zero-Guess)."""
    if isinstance(node, LlmNode):
        return NodeType.LLM_NODE
    if isinstance(node, CodeNode):
        return NodeType.CODE
    if isinstance(node, FlowNode):
        return NodeType.FLOW
    if isinstance(node, RemoteFlowNode):
        return NodeType.REMOTE_FLOW
    if isinstance(node, ExternalAPINode):
        return NodeType.EXTERNAL_API
    if isinstance(node, MCPNode):
        return NodeType.MCP
    if isinstance(node, ChannelNode):
        return NodeType.CHANNEL
    if isinstance(node, ResourceNode):
        return NodeType.RESOURCE
    raise ValueError(
        f"Не удалось определить type ноды для as_tool: {type(node).__name__}, задайте node_type"
    )


class NodeAsToolWrapper(BaseTool):
    """
    Обёртка над любой нодой для использования как tool.

    Поддерживает все типы нод.
    Args записываются в state, нода берет их через input_mapping.
    """

    _DEFAULT_LLM_TOOL_PARAMETERS_SCHEMA: ClassVar[JsonObject] = {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "Запрос к субагенту",
            }
        },
        "required": ["request"],
    }

    def __init__(
        self,
        node_config: NodeConfig | JsonObject,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        self.node_config: NodeConfig = (
            node_config
            if isinstance(node_config, NodeConfig)
            else NodeConfig.model_validate(node_config)
        )
        self.name: str = sanitize_tool_name(self.node_config.node_id)
        self.description: str = (
            self.node_config.description or f"Вызов ноды {self.node_config.name}"
        )
        self.tags: list[str] = self.node_config.tags or [self.node_config.type.value]
        self.is_nested_flow_tool: bool = self.node_config.type == NodeType.FLOW
        self._node: BaseNode | None = None
        self._bound_node: BaseNode | None = None
        self.container: ToolContainerRef | None = container

    @property
    @override
    def parameters(self) -> ToolParametersSchema:
        if self.node_config.parameters_schema is None:
            raise ValueError(
                f"Node-as-tool '{self.node_config.node_id}' requires parameters_schema"
            )
        schema = require_json_object(
            self.node_config.parameters_schema,
            f"node.{self.node_config.node_id}.parameters_schema",
        )
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            raise ValueError(
                f"Node-as-tool '{self.node_config.node_id}' parameters_schema must be object JSON Schema"
            )
        return schema

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
        node_type = _infer_node_type_for_tool(node)
        wrapper = cls(
            NodeConfig(
                node_id=node.node_id,
                type=node_type,
                name=tool_name or node.node_id,
                description=tool_description or node.description or f"Вызов ноды {node.node_id}",
                parameters_schema=cls._DEFAULT_LLM_TOOL_PARAMETERS_SCHEMA,
            )
        )
        wrapper._bound_node = node
        wrapper.container = node.container
        wrapper.name = sanitize_tool_name(tool_name or node.node_id)
        return wrapper

    async def _get_node(self) -> BaseNode:
        """Lazy создание ноды."""
        if self._bound_node is not None:
            return self._bound_node
        if self._node is None:
            container = self._require_container()
            node_dict = cast(
                JsonObject,
                self.node_config.model_dump(mode="json", exclude_none=True),
            )
            _ = node_dict.pop("tool_id", None)

            self._node = await create_node(
                self.node_config.node_id,
                node_dict,
                container=container,
            )

        return self._node

    def _require_container(self) -> FlowRuntimeContainer:
        if self.container is None:
            raise RuntimeError(f"Node tool '{self.name}' requires FlowRuntimeContainer")
        return as_flow_runtime_container(self.container)

    async def _execute_node_with_durable_context(
        self,
        node: BaseNode,
        node_id: str,
        node_type: NodeType,
        state: ExecutionState,
    ) -> ExecutionState:
        container = self._require_container()
        runtime = container.workflow_runtime

        state.current_nodes = [node_id]
        superstep_event = await runtime.record_state_event(
            state.session_id,
            state,
            event_type=WorkflowEventType.superstep_started,
            payload=SuperstepStartedPayload(current_nodes=[node_id]),
        )
        scheduled_event = await runtime.record_state_event(
            state.session_id,
            state,
            event_type=WorkflowEventType.node_scheduled,
            payload=NodeScheduledPayload(
                node_id=node_id,
                node_type=node_type.value,
                current_nodes=[node_id],
            ),
        )
        state.attach_durable_node_context(
            execution_branch_id=scheduled_event.execution_branch_id,
            node_schedule_sequence=scheduled_event.sequence,
            superstep_sequence=superstep_event.sequence,
        )

        before_state = ExecutionState.model_validate(
            state.model_dump(mode="python", exclude_none=False)
        )
        result_state = await node.execute(state)
        _ = await runtime.record_state_event(
            result_state.session_id,
            result_state,
            event_type=WorkflowEventType.node_write_recorded,
            payload=NodeWriteRecordedPayload(
                node_id=node_id,
                node_type=node_type.value,
                state_delta=build_state_delta(before_state, result_state),
            ),
        )
        _ = await runtime.record_state_event(
            result_state.session_id,
            result_state,
            event_type=WorkflowEventType.node_completed,
            payload=NodeCompletedPayload(node_id=node_id, node_type=node_type.value),
        )
        return result_state

    @override
    async def _run_impl(self, args: ToolArguments, state: ExecutionState) -> ToolResult:
        """
        Вызывает ноду. Для llm_node создает изолированный state и обрабатывает interrupt.
        """
        node_id = self.node_config.node_id
        node_type = self.node_config.type

        node = await self._get_node()
        logger.info(f"[wrapper:{node_id}] run with args: {list(args.keys())}")

        # Для llm_node создаем изолированный state
        if node_type == NodeType.LLM_NODE:
            return await self._run_llm_node(node, node_id, node_type, args, state)

        # Для остальных нод - простой вызов
        for key, value in args.items():
            state[key] = value

        result = await self._execute_node_with_durable_context(
            node,
            node_id,
            node_type,
            state,
        )
        return self._extract_response(result)

    async def _run_llm_node(
        self,
        node: BaseNode,
        node_id: str,
        node_type: NodeType,
        args: ToolArguments,
        parent_state: ExecutionState,
    ) -> ToolResult:
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
            result = await self._execute_node_with_durable_context(
                node,
                node_id,
                node_type,
                nested_state,
            )

            # Успешное завершение - копируем результат в родительский state
            self._copy_result_to_parent(nested_state, parent_state)

            # Сохраняем историю субагента
            InterruptManager.save_nested_state(parent_state, node_id, nested_state)

            return self._extract_response(result)

        except FlowInterrupt as e:
            # Сохраняем state субагента для resume
            logger.info(
                f"[wrapper:{node_id}] interrupt, saving nested_state: "
                + f"messages={len(nested_state.messages)}"
            )
            InterruptManager.save_nested_state(parent_state, node_id, nested_state)

            # Копируем interrupt_path из субагента в родительский state
            parent_state.interrupt_path = list(nested_state.interrupt_path)

            # Добавляем себя в начало пути
            InterruptManager.push_interrupt_path(
                parent_state,
                InterruptPathItem(
                    node_type=NodeType.LLM_NODE.value,
                    node_id=node_id,
                    tool_call=None,
                ),
            )

            logger.info(f"[wrapper:{node_id}] interrupt: {e.question[:50]}...")
            raise

    def _create_nested_state(
        self, parent_state: ExecutionState, args: ToolArguments
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
                + "'query', 'content' или 'request'"
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
            nested_state[key] = value

        return nested_state

    def _copy_result_to_parent(
        self, nested_state: ExecutionState, parent_state: ExecutionState
    ) -> None:
        """Копирует результат субагента в родительский state."""
        if nested_state.response:
            parent_state.response = nested_state.response

        parent_state.tool_results.update(nested_state.tool_results)

        # Копируем все extra поля которые субагент записал в state
        extra = nested_state.json_extra()
        if extra:
            for key, value in extra.items():
                parent_state[key] = value

    def _extract_response(self, result: ExecutionState | JsonValue) -> ToolResult:
        """Извлекает response из результата."""
        if isinstance(result, ExecutionState):
            if result.response is not None and str(result.response).strip() != "":
                return result.response
            if result.result is not None:
                return require_json_value(result.result, f"node.{self.node_config.node_id}.result")
            raise ValueError(
                "Нода завершилась без непустого state.response и без state.result "
                + "после вызова как tool"
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

    @override
    def __repr__(self) -> str:
        return f"NodeAsToolWrapper({self.node_config.node_id})"
