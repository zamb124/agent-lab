"""
Ноды для Flow runtime.

Нода = функция ExecutionState -> ExecutionState.
Маршрутизация через edges во Flow, не в нодах.

Типы нод:
- LlmNode - LLM нода с ReAct циклом
- CodeNode - выполнение кода (Python, JavaScript, Go)
- FlowNode - вложенный flow
- RemoteFlowNode - внешний flow по A2A протоколу
- CodeAgentNode - агент из дерева исходников + контейнер guest_runtime
- ExternalAPINode - вызов внешнего HTTP API
- MCPNode - вызов MCP tool
- DatasourceNode - живая БД (DatasourceProtocol)
- ReflectionNode - typed critic / test-time compute gate
- ResourceNode - нода-ресурс на графе (identity / pass-through)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import ClassVar, Literal, TypeAlias, overload, override

from a2a.types import Artifact, Message, Part
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.contracts import (
    ChannelRegistryProtocol,
    FlowFactoryProtocol,
    RuntimeFlowProtocol,
    ToolRegistryProtocol,
)
from apps.flows.src.durable_execution import (
    ChildWorkflowLifecyclePayload,
    DurableWorkflowRuntime,
    ExecutionStateDelta,
    HandoffResumedPayload,
    RunStartedPayload,
    SideEffectPolicy,
    SuperstepCommittedPayload,
    WorkflowEventType,
    WorkflowExecutionPosition,
    apply_state_delta,
    build_state_delta,
    hash_state_json,
)
from apps.flows.src.flow_ui.effects import apply_capability_platform_effects
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models import (
    MCPServerConfig,
    NodeConfig,
    NodeLLMConfig,
    ReactConfig,
    ResourceReference,
    ResourceReferenceInput,
    ToolReference,
)
from apps.flows.src.models.agent_skill import AgentSkill
from apps.flows.src.models.enums import ChannelType, NodeToolCallType, NodeType
from apps.flows.src.models.exception_absorb_allow import ExceptionAbsorbAllowName
from apps.flows.src.models.external_api import ExternalAPIConfig, HTTPMethod
from apps.flows.src.models.hitl_schemas import HitlInterruptSnapshot, build_hitl_handoff_command
from apps.flows.src.models.node_config import LLMCapability
from apps.flows.src.models.resource import ResourceType
from apps.flows.src.reflection import (
    CriticPolicy,
    ReflectionCritiqueResult,
    ReflectionGateResult,
    ReflectionRecord,
    ReflectionTargetSnapshot,
    evaluate_reflection_gate,
)
from apps.flows.src.runners.remote import load_sandbox_capability_manifest
from apps.flows.src.runtime.agent_skill_runtime import AgentSkillRuntimeHost
from apps.flows.src.runtime.effective_llm_config import resolve_effective_llm_config_for_node
from apps.flows.src.runtime.exception_policy import node_exception_policy, should_absorb_exception
from apps.flows.src.runtime.exceptions import (
    BreakpointInterrupt,
    FlowInterrupt,
    RemoteTaskParked,
)
from apps.flows.src.runtime.execution_context import (
    FlowExecutionContext,
    execution_context_for,
)
from apps.flows.src.runtime.flow_interface_context import current_flow_interface
from apps.flows.src.runtime.llm_context_memory import resolve_memory_context_source_for_runtime
from apps.flows.src.runtime.llm_context_memory_store import RAGLLMContextMemoryStore
from apps.flows.src.runtime.llm_context_rag import resolve_rag_context_source_registry_for_runtime
from apps.flows.src.runtime.llm_context_resource import resolve_llm_context_policy_for_runtime
from apps.flows.src.runtime.llm_resource_config import (
    infer_unique_llm_resource_key_from_merged_maps,
    resolve_llm_config_with_resource_key,
)
from apps.flows.src.runtime.runners import LlmNodeRunner
from apps.flows.src.services.code_agent_source_service import CodeAgentSourceService
from apps.flows.src.services.datasources.executors import build_datasource_executors
from apps.flows.src.services.external_api_client import ExternalAPIClient
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.flow_ui_cards import card_block_id, show_reflection
from apps.flows.src.services.handoff_orchestrator_service import HandoffOrchestratorService
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from apps.flows.src.services.hitl_work_item_service import (
    HANDOFF_PREVIEW_MAX_LEN,
    HitlWorkItemService,
)
from apps.flows.src.services.mcp_client import MCPClient
from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from apps.flows.src.state import (
    ChildWorkflowLink,
    ChildWorkflowStatus,
    ExecutionExceptionRecord,
    ExecutionState,
    InterruptPathItem,
    parse_interrupt_body_from_external_dict,
)
from apps.flows.src.state.execution_state import ExecutionStateValue
from apps.flows.src.state.interrupt import HandoffMode, OperatorTaskInterrupt
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.state.mutation_policy import (
    forbid_frozen_update_key,
    should_skip_field_on_user_returned_state_copy,
)
from apps.flows.src.streaming.emitter import EmitterFactory
from apps.flows.src.tasks.task_names import TASK_FLOWS_REMOTE_TASK_FINISHED
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.materialize import ToolMaterializeInput
from apps.flows.tools.flows.agent_skill_tools import load_agent_skill, read_agent_skill_reference
from apps.flows.tools.tables.tables import TABLES_TOOLS
from core.a2a import artifact_from_json_dict, mapping_from_struct, struct_from_mapping
from core.a2a.submit import submit_a2a_call
from core.ai.providers import LLM_CAPABILITY_VALUES
from core.ai.runtime import create_llm_client_from_call_config
from core.authz.service import AuthzService
from core.billing.service import BillingService
from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    PlatformEffectEnvelope,
    execution_token_exp,
    issue_execution_token,
)
from core.clients.a2a_client import A2AClient, A2AClientError
from core.clients.guest_runtime_client import GuestRuntimeClient
from core.clients.llm.mock_control import (
    MOCK_MISS,
    MockMiss,
    resolve_entity_node_mock_result,
)
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.context import get_context as get_request_context
from core.datasources.models import DatasourceOperation
from core.datasources.service import DatasourceExecutors, DatasourceService
from core.errors import NodeWallClockTimeoutError
from core.guest_runtime.env import (
    guest_env_key_is_reserved,
    guest_env_key_is_valid,
    validate_guest_env,
)
from core.guest_runtime.models import GuestEnsureLeaseRequest, GuestInvokeKind, GuestLanguage
from core.integrations.mcp import mcp_tool_reference_id
from core.llm_context import (
    LLMContextPatch,
    LLMContextProfile,
    LLMContextSource,
    LLMContextSourceRegistry,
)
from core.logging import get_log_context, get_logger
from core.mail.service import MailService
from core.namespace.service import NamespaceService
from core.test_scope import resolve_test_scope
from core.text_transforms.service import TextTransformService
from core.tracing.attributes import (
    ATTR_NODE_ID,
    ATTR_REFLECTION_GATE,
    ATTR_REFLECTION_POLICY_ID,
    ATTR_REFLECTION_TARGET,
)
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object, require_json_value
from core.variables import VariableResolver, VarResolver
from core.variables.service import VariablesService
from core.worktracker.models import WorkItem, WorkItemState

logger = get_logger(__name__)
NodeInputs: TypeAlias = JsonObject
NodeRunResult: TypeAlias = ExecutionState | JsonValue


def _mcp_side_effect_policy(annotations: JsonObject | None) -> SideEffectPolicy:
    if annotations is None:
        return SideEffectPolicy.non_idempotent
    read_only = annotations.get("readOnlyHint")
    idempotent = annotations.get("idempotentHint")
    if read_only is True or idempotent is True:
        return SideEffectPolicy.idempotent
    return SideEffectPolicy.non_idempotent


DURABLE_CONTEXT_NODE_TYPES: frozenset[NodeType] = frozenset(
    {
        NodeType.LLM_NODE,
        NodeType.CODE,
        NodeType.FLOW,
        NodeType.REMOTE_FLOW,
        NodeType.CODE_AGENT,
        NodeType.EXTERNAL_API,
        NodeType.MCP,
        NodeType.DATASOURCE,
        NodeType.CHANNEL,
        NodeType.HITL_NODE,
        NodeType.REFLECTION,
    }
)


def _config_mapping(config: JsonObject, field_name: str) -> JsonObject | None:
    if field_name not in config or config[field_name] is None:
        return None
    value = config[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name}: expected object")
    return require_json_object(value, field_name)


def _config_mapping_default(config: JsonObject, field_name: str) -> JsonObject:
    value = _config_mapping(config, field_name)
    if value is None:
        return {}
    return value


def _config_string_map(config: JsonObject, field_name: str) -> dict[str, str] | None:
    value = _config_mapping(config, field_name)
    if value is None:
        return None
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise ValueError(f"{field_name}.{key}: expected string")
        out[key] = item
    return out


def _config_string_map_default(config: JsonObject, field_name: str) -> dict[str, str]:
    value = _config_string_map(config, field_name)
    if value is None:
        return {}
    return value


def _config_optional_string(config: JsonObject, field_name: str) -> str | None:
    if field_name not in config or config[field_name] is None:
        return None
    value = config[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name}: expected string")
    return value


def _config_string(config: JsonObject, field_name: str, default: str) -> str:
    value = _config_optional_string(config, field_name)
    if value is None:
        return default
    return value


def _config_bool(config: JsonObject, field_name: str, default: bool) -> bool:
    if field_name not in config or config[field_name] is None:
        return default
    value = config[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"{field_name}: expected bool")
    return value


def _config_optional_int(config: JsonObject, field_name: str) -> int | None:
    if field_name not in config or config[field_name] is None:
        return None
    value = config[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name}: expected int")
    return value


def _config_float(config: JsonObject, field_name: str, default: float) -> float:
    if field_name not in config or config[field_name] is None:
        return default
    value = config[field_name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name}: expected number")
    return float(value)


def _config_json_object(
    config: JsonObject,
    field_name: str,
) -> JsonObject | None:
    value = _config_mapping(config, field_name)
    if value is None:
        return None
    return value


def _config_messages_filter(
    config: JsonObject,
    field_name: str,
) -> Literal["all", "own"] | list[str]:
    if field_name not in config or config[field_name] is None:
        return "all"
    value = config[field_name]
    if value in ("all", "own"):
        return value
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{field_name}: list must contain non-empty strings")
            out.append(item)
        return out
    raise ValueError(f"{field_name}: expected 'all', 'own' or list[str]")


def _config_tool_refs(config: JsonObject, field_name: str) -> list[str | ToolMaterializeInput]:
    if field_name not in config or config[field_name] is None:
        return []
    value = config[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{field_name}: expected list")
    out: list[str | ToolMaterializeInput] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(require_json_object(item, f"{field_name}[]"))
            continue
        raise ValueError(f"{field_name}: expected string or object")
    return out


def _config_string_list(config: JsonObject, field_name: str) -> list[str]:
    if field_name not in config or config[field_name] is None:
        return []
    value = config[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{field_name}: expected list[str]")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}: expected non-empty strings")
        normalized = item.strip()
        if normalized in seen:
            raise ValueError(f"{field_name}: duplicate id {normalized}")
        seen.add(normalized)
        out.append(normalized)
    return out


def _config_parameters_schema(config: JsonObject) -> JsonObject | None:
    value = _config_mapping(config, "parameters_schema")
    if value is None:
        return None
    schema = require_json_object(value, "parameters_schema")
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), Mapping):
        raise ValueError("parameters_schema: expected a JSON Schema object with properties")
    return schema


def _config_resource_refs(
    config: JsonObject, field_name: str = "resources"
) -> dict[str, ResourceReferenceInput]:
    raw = _config_mapping_default(config, field_name)
    out: dict[str, ResourceReferenceInput] = {}
    for resource_key, resource_value in raw.items():
        if not isinstance(resource_value, Mapping):
            raise ValueError(f"{field_name}.{resource_key}: expected object")
        out[resource_key] = require_json_object(
            resource_value,
            f"{field_name}.{resource_key}",
        )
    return out


class NodeRunMethod:
    """Callable-обёртка для node.run(); TaskIQ kick на границе task/API через enqueue."""

    def __init__(self, node: BaseNode):
        self._node: BaseNode = node

    async def __call__(self, state: ExecutionState) -> ExecutionState:
        """Прямой вызов в текущем процессе."""
        return await self._node.execute(state)

    async def kiq(self, state: ExecutionState) -> ExecutionState:
        """Диспетчеризация TaskIQ живёт на границе task/API, не внутри runtime-нод."""
        _ = state
        raise RuntimeError(
            "node.run TaskIQ kick is not part of runtime; use execute_node task at the boundary"
        )


class NodeRunDescriptor:
    """Descriptor для node.run"""

    @overload
    def __get__(
        self,
        obj: None,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunDescriptor: ...

    @overload
    def __get__(
        self,
        obj: BaseNode,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunMethod: ...

    def __get__(
        self,
        obj: BaseNode | None,
        objtype: type[BaseNode] | None = None,
    ) -> NodeRunDescriptor | NodeRunMethod:
        if obj is None:
            return self
        return NodeRunMethod(obj)


class BaseNode(ABC):
    """
    Базовый класс для нод. Node = функция ExecutionState -> ExecutionState.

    Template Method паттерн:
    - run(state) — единая точка входа; TaskIQ kick только через enqueue на границе
    - _resolve_inputs() - единообразный резолвинг input_mapping
    - get_filtered_messages() - фильтрация messages
    - _run_impl() - конкретная логика каждой ноды

    Конфигурация:
    - input_mapping: Dict - маппинг входных данных из state
    - output_mapping: Dict[str, str] - маппинг полей результата -> state fields
    - save_to_messages: bool - добавлять результат в messages
    - message_field: str - какое поле писать в messages (по умолчанию diff стейта)
    - messages_filter: "all" / "own" / List[str] — срез по metadata.node_id

    Контракт _run_impl() для ВСЕХ нод:
    - Возвращает JSON-значение или ExecutionState
    - dict: поля записываются в state через output_mapping
    - не dict и не None: записывается в state.result
    - None: ничего не записывается
    """

    name: ClassVar[str] = "node"
    description: ClassVar[str | None] = None
    node_type: ClassVar[NodeType | None] = None

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
    ):
        self.node_id: str = node_id
        self.config: JsonObject = dict(config) if config is not None else {}
        raw_node_type = self.config.get("type")
        if not isinstance(raw_node_type, str) or not raw_node_type:
            raise ValueError(f"Node '{self.node_id}': config.type is required")
        if self.node_type is not None and raw_node_type != self.node_type.value:
            raise ValueError(
                f"Node '{self.node_id}': config.type must be {self.node_type.value!r}, "
                + f"got {raw_node_type!r}"
            )
        self.execution: FlowExecutionContext = execution
        self.redis_client: RedisClient = redis_client
        self.input_mapping: JsonObject | None = _config_mapping(self.config, "input_mapping")
        self.output_mapping: dict[str, str] | None = _config_string_map(
            self.config, "output_mapping"
        )
        self.save_to_messages: bool = _config_bool(self.config, "save_to_messages", False)
        self.message_field: str | None = _config_optional_string(self.config, "message_field")
        self.messages_filter: Literal["all", "own"] | list[str] = _config_messages_filter(
            self.config,
            "messages_filter",
        )

    @classmethod
    def from_config(
        cls,
        node_id: str,
        config: JsonObject,
        *,
        node_constructor: NodeConstructor,
        tool_registry: ToolRegistryProtocol,
        flow_factory: FlowFactoryProtocol,
    ) -> "BaseNode":
        """Создает ноду из конфига."""
        return node_constructor.build(
            cls,
            node_id,
            config,
            tool_registry=tool_registry,
            flow_factory=flow_factory,
        )

    def _requires_durable_context(self) -> bool:
        return self.node_type in DURABLE_CONTEXT_NODE_TYPES

    async def _require_durable_context(self, state: ExecutionState) -> None:
        if not self._requires_durable_context():
            return
        position = await self.execution.active_position(state.session_id)
        if position is None:
            raise RuntimeError(
                f"Node '{self.node_id}' requires durable workflow instance "
                + f"before execution: {state.session_id!r}"
            )
        if state.durable_execution_branch_id is None:
            raise RuntimeError(f"Node '{self.node_id}' requires durable execution_branch_id")
        if state.durable_node_schedule_sequence is None:
            raise RuntimeError(f"Node '{self.node_id}' requires NodeScheduled.sequence")

    async def _run_durable_activity(
        self,
        state: ExecutionState,
        *,
        activity_type: str,
        input_payload: JsonObject,
        side_effect_policy: SideEffectPolicy,
        invoke: Callable[[], Awaitable[NodeRunResult]],
        activity_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> NodeRunResult:
        execution_position = await self.execution.active_position(state.session_id)
        if execution_position is None:
            raise RuntimeError(
                f"Workflow instance is required before scheduling activity for node '{self.node_id}'"
            )
        position_branch = execution_position.execution_branch_id
        state_branch = state.durable_execution_branch_id
        if state_branch is None:
            raise RuntimeError("Durable activity requires execution_branch_id on ExecutionState")
        if state_branch != position_branch:
            raise RuntimeError(
                "Durable activity branch mismatch: "
                + f"state={state_branch!r}, active={position_branch!r}"
            )
        resolved_activity_id = (
            activity_id
            if activity_id is not None
            else self._durable_activity_id(state, activity_type, input_payload)
        )
        resolved_idempotency_key = (
            idempotency_key if idempotency_key is not None else resolved_activity_id
        )
        completed = await self.execution.activities.schedule(
            session_id=state.session_id,
            activity_id=resolved_activity_id,
            activity_type=activity_type,
            input_payload=input_payload,
            node_id=self.node_id,
            idempotency_key=resolved_idempotency_key,
            side_effect_policy=side_effect_policy,
        )
        if completed is not None:
            delta_raw = completed.get("state_delta")
            if isinstance(delta_raw, dict):
                replayed_state = apply_state_delta(
                    state,
                    ExecutionStateDelta.model_validate(delta_raw),
                )
                self._copy_state_back(replayed_state, state, full_trust=True)
            return require_json_value(
                completed.get("result"),
                f"activity.{activity_type}.result",
            )

        started = await self.execution.activities.start(resolved_activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark activity as started: {resolved_activity_id!r}")
        before_state = ExecutionState.model_validate(
            state.model_dump(mode="python", exclude_none=False)
        )
        try:
            result = await invoke()
        except RemoteTaskParked:
            # Парк — activity остаётся `started` до webhook-continuation.
            raise
        except Exception as exc:
            completed_failed = await self.execution.activities.complete(
                activity_id=resolved_activity_id,
                error=str(exc),
            )
            if not completed_failed:
                raise RuntimeError(
                    f"Failed to mark activity as failed: {resolved_activity_id!r}"
                ) from exc
            raise

        state_delta = build_state_delta(before_state, state)
        result_json = require_json_object(
            {
                "result": (
                    require_json_value(result, f"activity.{activity_type}.result")
                    if result is not None
                    else None
                ),
                "state_delta": state_delta.model_dump(mode="json", exclude_none=False),
            },
            f"activity.{activity_type}.result_json",
        )
        completed_ok = await self.execution.activities.complete(
            activity_id=resolved_activity_id,
            result_json=result_json,
        )
        if not completed_ok:
            raise RuntimeError(f"Failed to mark activity as completed: {resolved_activity_id!r}")
        return result

    def _durable_activity_id(
        self,
        state: ExecutionState,
        activity_type: str,
        input_payload: JsonObject,
    ) -> str:
        input_hash = hash_state_json(input_payload)
        execution_branch_id = state.durable_execution_branch_id
        if execution_branch_id is None:
            raise RuntimeError("Durable activity requires execution_branch_id")

        schedule_sequence = state.durable_node_schedule_sequence
        if schedule_sequence is None:
            raise RuntimeError("Durable activity requires NodeScheduled.sequence")

        schedule_part = f"schedule:{schedule_sequence}"

        return (
            f"{state.session_id}:{execution_branch_id}:node:{self.node_id}:"
            + f"{activity_type}:{schedule_part}:input:{input_hash}"
        )

    @staticmethod
    def _state_hash_for_activity(state: ExecutionState) -> str:
        payload = require_json_object(
            state.model_dump(mode="json", exclude_none=False),
            "activity.state",
        )
        _ = payload.pop("flow_config", None)
        return hash_state_json(payload)

    def _resolve_inputs(self, state: ExecutionState) -> NodeInputs:
        """
        Единообразный резолвинг input_mapping для всех типов нод.

        Возвращает:
            Dict с резолвнутыми значениями из input_mapping
        """
        if not self.input_mapping:
            return {}
        return require_json_object(
            MappingResolver.build_mapped_state(self.input_mapping, state),
            f"node.{self.node_id}.input_mapping",
        )

    def get_filtered_messages(self, state: ExecutionState) -> list[Message]:
        """
        Возвращает отфильтрованные messages.

        Фильтры:
        - "all" — все сообщения
        - "own" — только сообщения с metadata.node_id == node_id этой ноды
        - List[str] — только сообщения, у которых metadata.node_id входит в список
        """
        all_messages = state.messages or []

        if self.messages_filter == "all":
            return list(all_messages)

        if self.messages_filter == "own":
            return [m for m in all_messages if self._get_message_node_id(m) == self.node_id]

        allowed = set(self.messages_filter)
        return [m for m in all_messages if self._get_message_node_id(m) in allowed]

    def _get_filtered_messages(self, state: ExecutionState) -> list[Message]:
        return self.get_filtered_messages(state)

    def _append_to_messages(self, state: ExecutionState, result: NodeRunResult) -> None:
        """Добавляет результат в messages с маркировкой node_id."""
        text = str(result) if not isinstance(result, str) else result
        message = Message(
            message_id=str(uuid.uuid4()),
            role=ROLE_AGENT,
            parts=[Part(text=text)],
            metadata=struct_from_mapping({"node_id": self.node_id}),
            task_id=state.task_id,
        )
        state.messages.append(message)

    @staticmethod
    def _get_message_node_id(msg: Message) -> str | None:
        """Извлекает node_id из metadata сообщения."""
        if not msg.HasField("metadata"):
            return None
        metadata = mapping_from_struct(msg.metadata)
        node_id = metadata.get("node_id")
        return node_id if isinstance(node_id, str) else None

    # Descriptor для унифицированного вызова: node.run(state)
    run: ClassVar[NodeRunDescriptor] = NodeRunDescriptor()

    async def execute(self, state: ExecutionState) -> ExecutionState:
        """
        Выполняет ноду в текущем процессе.

        1. Сохранение snapshot для diff (если save_to_messages без message_field)
        2. Резолвинг input_mapping -> inputs
        3. Выполнение _run_impl(state, inputs)
        4. Обработка результата:
           - ExecutionState: мержим в текущий state
           - dict: записываем поля в state через output_mapping
        5. Добавление в messages если save_to_messages=True
        """
        await self._require_durable_context(state)

        state_before: JsonObject | None = None
        if self.save_to_messages and not self.message_field:
            state_before = require_json_object(
                state.model_dump(mode="json", exclude_none=False),
                "state_before",
            )

        inputs = self._resolve_inputs(state)

        # Mock Control: для не-LLM нод (code/function/...) и вложенных flow берём
        # результат из mock-очереди вместо реального запуска. LLM-ноды мокаются
        # внутри runner (per-node очередь LLM-ответов), не здесь.
        mock_node_result = await self._resolve_node_mock_result(state)
        result: NodeRunResult
        if not isinstance(mock_node_result, MockMiss):
            result = mock_node_result
            if result is not None:
                self._apply_output_mapping(state, result)
            if self.save_to_messages:
                message_content = self._get_message_content(state, state_before, result)
                if message_content:
                    self._append_to_messages(state, message_content)
            return state

        node_timeout = self.config.get("node_timeout_seconds")
        nto: int | None = None
        try:
            if node_timeout is not None:
                if isinstance(node_timeout, bool) or not isinstance(node_timeout, int):
                    raise ValueError("node_timeout_seconds: expected integer")
                nto = node_timeout
                result = await asyncio.wait_for(
                    self._run_impl(state, inputs),
                    timeout=float(nto),
                )
            else:
                result = await self._run_impl(state, inputs)
        except asyncio.TimeoutError as e:
            if nto is None:
                raise
            raise NodeWallClockTimeoutError(self.node_id, nto) from e
        except FlowInterrupt, BreakpointInterrupt:
            raise
        except asyncio.CancelledError:
            raise
        except SystemExit, KeyboardInterrupt:
            raise
        except Exception as e:
            enabled, allow_types = node_exception_policy(self.config)
            if not should_absorb_exception(e, enabled=enabled, allow_types=allow_types):
                raise
            state.execution_exceptions.append(
                ExecutionExceptionRecord(
                    node_id=self.node_id,
                    source="node_run",
                    exception_type=type(e).__name__,
                    message=str(e),
                )
            )
            exception_result: JsonObject = {
                "error": True,
                "error_type": type(e).__name__,
                "message": str(e),
            }
            result = exception_result

        if result is not None:
            if isinstance(result, ExecutionState):
                self._copy_state_back(result, state, full_trust=False)
            else:
                self._apply_output_mapping(state, result)

        if self.save_to_messages:
            message_content = self._get_message_content(state, state_before, result)
            if message_content:
                self._append_to_messages(state, message_content)

        return state

    async def _resolve_node_mock_result(self, state: ExecutionState) -> JsonValue | MockMiss:
        """
        Результат ноды из Mock Control или `MOCK_MISS` (нужен реальный запуск).

        LLM-ноды не мокаются здесь — у них per-node очередь LLM-ответов в runner.
        Вложенный flow мокается по `flow_id`, остальные ноды — по `node_id`.
        """
        if self.node_type == NodeType.LLM_NODE:
            return MOCK_MISS
        if self.node_type == NodeType.FLOW:
            flow_id = self.config.get("flow_id")
            if not isinstance(flow_id, str) or not flow_id.strip():
                return MOCK_MISS
            return await resolve_entity_node_mock_result(
                self.redis_client, state.session_id, "flow", flow_id
            )
        return await resolve_entity_node_mock_result(
            self.redis_client, state.session_id, "node", self.node_id
        )

    def _apply_output_mapping(self, state: ExecutionState, result: JsonValue) -> None:
        """
        Записывает результат в state через output_mapping.

        Если result - dict:
          - С output_mapping: result[key] -> state[mapped_field]
          - Без output_mapping: result[key] -> state[key] (напрямую)
        Если result - не dict:
          - Записываем в state.result
        """
        if isinstance(result, dict):
            if self.output_mapping:
                for result_key, state_field in self.output_mapping.items():
                    if result_key in result:
                        forbid_frozen_update_key(state_field, reason="output_mapping")
                        state[state_field] = result[result_key]
            else:
                for key, value in result.items():
                    forbid_frozen_update_key(key, reason="output_mapping")
                    state[key] = value
        else:
            state["result"] = result

    def _get_message_content(
        self,
        state: ExecutionState,
        state_before: JsonObject | None,
        result: NodeRunResult | None,
    ) -> str | None:
        """
        Определяет что записать в messages.

        Приоритет поиска message_field:
        1. result[message_field] если result - dict
        2. state.message_field
        """
        if self.message_field:
            value = None
            if isinstance(result, dict) and self.message_field in result:
                value = result[self.message_field]
            else:
                value = MappingResolver.get_nested_value(state, self.message_field)
            return str(value) if value is not None else None
        elif state_before:
            return self._compute_state_diff(state_before, state)
        else:
            return str(result) if result is not None else None

    def _compute_state_diff(
        self,
        state_before: JsonObject,
        state_after: ExecutionState,
    ) -> str | None:
        """Вычисляет diff между состояниями для записи в messages."""
        state_after_dict = require_json_object(
            state_after.model_dump(mode="json", exclude_none=False),
            "state_after",
        )

        skip_fields = {"messages", "prompt_history", "node_history", "nested_states"}

        diff_parts: list[str] = []
        for key, new_value in state_after_dict.items():
            if key in skip_fields:
                continue
            old_value = state_before.get(key)
            if old_value != new_value and new_value is not None:
                diff_parts.append(f"{key}: {new_value}")

        if not diff_parts:
            return None
        return "\n".join(diff_parts)

    @abstractmethod
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Конкретная логика ноды.

        Аргументы:
            state: ExecutionState для чтения/записи
            inputs: Резолвнутые данные из input_mapping

        Возвращает:
            Результат (dict - поля записываются в state через output_mapping)
        """
        pass

    def _copy_state_back(
        self,
        source: ExecutionState,
        target: ExecutionState,
        *,
        full_trust: bool = True,
    ) -> None:
        """Копирует изменения из source в target. full_trust=False — не переносить системные поля."""
        source_fields = source.__dict__
        for field_name in ExecutionState.model_fields:
            if not full_trust and should_skip_field_on_user_returned_state_copy(field_name):
                continue
            if field_name in source_fields:
                target[field_name] = source_fields[field_name]

        # Очередь ui-событий — PrivateAttr, не model field: без переноса карточки
        # инструментов не дошли бы до flush в конце superstep.
        target.queue_ui_events(source.drain_ui_events())

        extra_src = require_json_object(
            source.__pydantic_extra__ or {},
            "source.extra",
        )
        if extra_src:
            if target.__pydantic_extra__ is None:
                target.__pydantic_extra__ = {}
            if full_trust:
                target.__pydantic_extra__.update(extra_src)
            else:
                for ek, ev in extra_src.items():
                    if should_skip_field_on_user_returned_state_copy(ek):
                        continue
                    target[ek] = ev

    def _prepare_state(self, state: ExecutionState, inputs: NodeInputs) -> ExecutionState:
        """
        Создает state для вложенного выполнения.
        Применяет inputs и фильтрует messages.
        Сбрасывает current_nodes чтобы вложенный flow начал со своего entry.
        """
        new_state = state.runtime_copy()

        for key, value in inputs.items():
            new_state[key] = value

        new_state.messages = self.get_filtered_messages(state)

        # Сбрасываем current_nodes — вложенный flow начнёт со своего entry
        new_state.current_nodes = []

        return new_state


class LlmNode(BaseNode):
    """
    LLM нода (ReAct цикл + tools).

    Объединяет функционал ноды графа и исполнителя.
    Может использоваться как базовый класс для кастомных нод.

    Атрибуты класса (для кастомных нод):
    - name: имя ноды
    - description: описание
    - prompt: системный промпт
    - tools: список tools

    Параметры конструктора (для ноды графа):
    - node_id: ID ноды в графе
    - prompt: шаблон промпта
    - tools: список inline tool configs
    - llm_config: конфигурация LLM
    - input_mapping: маппинг входных данных

    Хуки для кастомизации:
    - before_prompt_render: перед рендерингом промпта
    - after_prompt_render: после рендеринга промпта
    """

    # Атрибуты для кастомных классов
    name: ClassVar[str] = "llm_node"
    node_type: ClassVar[NodeType | None] = NodeType.LLM_NODE
    description: ClassVar[str | None] = None
    prompt: ClassVar[str | None] = None
    tools: ClassVar[list[BaseTool]] = []

    def __init__(
        self,
        node_id: str | None = None,
        config: JsonObject | None = None,
        node_config: NodeConfig | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        flow_factory: FlowFactoryProtocol,
        llm_context_memory_store: RAGLLMContextMemoryStore,
        namespace_service: NamespaceService,
        authz_service: AuthzService,
        tool_registry: ToolRegistryProtocol,
        workflow_runtime: DurableWorkflowRuntime,
        text_transform_service: TextTransformService,
        billing_service: BillingService,
        emitter_factory: EmitterFactory,
    ):
        super().__init__(
            node_id or self.name,
            config,
            execution=execution,
            redis_client=redis_client,
        )
        self.flow_factory: FlowFactoryProtocol = flow_factory
        self.llm_context_memory_store: RAGLLMContextMemoryStore = llm_context_memory_store
        self.namespace_service: NamespaceService = namespace_service
        self.authz_service: AuthzService = authz_service
        self.tool_registry: ToolRegistryProtocol = tool_registry
        self.workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self.text_transform_service: TextTransformService = text_transform_service
        self.billing_service: BillingService = billing_service
        self.emitter_factory: EmitterFactory = emitter_factory
        cfg = self.config

        self.prompt_template: str = self.prompt or _config_string(cfg, "prompt", "")
        self.tool_refs: list[str | ToolMaterializeInput] = _config_tool_refs(cfg, "tools")
        self.agent_skill_ids: list[str] = _config_string_list(cfg, "agent_skills")
        raw_llm = cfg.get("llm")
        if isinstance(raw_llm, dict):
            llm_config_dict: JsonObject = require_json_object(raw_llm, "llm")
        else:
            llm_config_dict = {}
        self.llm_config_dict: JsonObject = llm_config_dict

        self._node_config: NodeConfig | None = node_config
        self._runner: LlmNodeRunner | None = None
        self._loaded_tools: list[BaseTool] | None = None
        self._agent_skill_host: AgentSkillRuntimeHost | None = None
        if node_config is not None:
            self.messages_filter: Literal["all", "own"] | list[str] = node_config.messages_filter
            if node_config.agent_skills:
                self.agent_skill_ids = list(node_config.agent_skills)

    def _prepare_llm_runner_state(
        self, state: ExecutionState, inputs: NodeInputs
    ) -> ExecutionState:
        """
        Копия state для раннера LLM: общий список messages с родителем (полный лог), без подмены фильтром.
        """
        new_state = state.runtime_copy()
        for key, value in inputs.items():
            new_state[key] = value
        # input_mapping is the explicit contract for values consumed by this
        # LLM node. Make mapped targets available to the prompt resolver as
        # {target}; node_config.local_variables still wins later in the runner.
        new_state.variables = {
            **require_json_object(state.variables or {}, "state.variables"),
            **dict(inputs),
        }
        new_state.messages = state.messages
        new_state.current_nodes = list(state.current_nodes)
        return new_state

    @property
    def llm_node_id(self) -> str:
        """ID ноды"""
        if self._node_config:
            return self._node_config.node_id
        return self.node_id

    @property
    def llm_config(self) -> JsonObject:
        """LLM конфигурация."""
        return self.llm_config_dict

    def _get_typed_llm_config(self) -> NodeLLMConfig | None:
        if self._node_config and self._node_config.llm:
            return self._node_config.llm
        if not self.llm_config_dict:
            return None
        return NodeLLMConfig.model_validate(self.llm_config_dict)

    @property
    def llm_node_name(self) -> str:
        """Название ноды"""
        if self._node_config:
            return self._node_config.name
        return self.name

    @property
    def llm_node_description(self) -> str | None:
        """Описание ноды"""
        if self._node_config and self._node_config.description:
            return self._node_config.description
        return self.description

    @property
    def llm_node_prompt(self) -> str | None:
        """Промпт ноды"""
        if self._node_config and self._node_config.prompt:
            return self._node_config.prompt
        return self.prompt_template or self.prompt

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Выполняет ReAct цикл.

        _copy_state_back мержит все изменения из рабочей копии state в исходный state.
        При structured_output возвращает dict с полями из JSON ответа.
        """
        runner_state = self._prepare_llm_runner_state(state, inputs)

        # structured_output_result используется как одноразовый канал передачи
        # JSON-ответа structured-ноды в output_mapping. Его нельзя переносить
        # между нодами — иначе следующая нода "наследует" результат и будет
        # выглядеть как будто вернула structured output, даже если это не так.
        runner_state.clear_structured_output_result()

        logger.info("flows.node.llm_started", node_id=self.node_id)

        content = runner_state.content or ""
        input_data: JsonObject = {"content": content}

        try:
            runner = await self.get_runner(runner_state)
            async for _ in runner.run(input_data, runner_state):
                pass
        finally:
            self._copy_state_back(runner_state, state)

        # При structured output возвращаем dict для записи в state через output_mapping
        structured_result = runner_state.structured_output_result
        if structured_result is not None:
            runner_state.clear_structured_output_result()
            structured_payload = require_json_value(
                structured_result,
                "state.structured_output_result",
            )
            state.response = json.dumps(structured_payload, ensure_ascii=False)
            return structured_payload

        return {"response": state.response} if state.response else None

    async def get_runner(self, state: ExecutionState | None = None) -> LlmNodeRunner:
        """Возвращает runner для LlmNode."""
        if self._runner is not None:
            return self._runner

        tools = await self.get_tools(state)
        prompt = self.llm_node_prompt or ""

        base = self._node_config or self._create_default_config()
        config = await self._resolve_effective_node_config(base, state)
        llm_context_policy = await self._resolve_effective_llm_context_policy(config, state)
        llm_context_source_registry = await self._resolve_llm_context_source_registry(
            config,
            state,
            llm_context_policy,
        )
        agent_skill_host = await self._ensure_agent_skill_host()

        self._runner = LlmNodeRunner(
            node_config=config,
            tools=tools,
            llm=None,
            prompt=prompt,
            llm_node=self,
            workflow_runtime=self.workflow_runtime,
            memory_store=self.llm_context_memory_store,
            text_transform_service=self.text_transform_service,
            billing_service=self.billing_service,
            emitter_factory=self.emitter_factory,
            redis_client=self.redis_client,
            tool_registry=self.tool_registry,
            llm_context_policy=llm_context_policy,
            llm_context_source_registry=llm_context_source_registry,
            agent_skill_host=agent_skill_host,
        )

        return self._runner

    async def get_tools(self, state: ExecutionState | None = None) -> list[BaseTool]:
        """Возвращает список tools."""
        if self._loaded_tools is not None:
            tools = await self._ensure_agent_skill_meta_tools(self._loaded_tools)
            tools = await self._ensure_data_table_tools(tools, state)
            self._loaded_tools = tools
            return tools

        tools: list[BaseTool]
        if self.tool_refs:
            tools = await self._load_tools(state)
        else:
            tools = list(self.tools)

        tools = await self._ensure_agent_skill_meta_tools(tools)
        tools = await self._ensure_data_table_tools(tools, state)
        self._loaded_tools = tools
        return tools

    async def _ensure_agent_skill_host(self) -> AgentSkillRuntimeHost | None:
        if not self.agent_skill_ids:
            return None
        if self._agent_skill_host is not None:
            return self._agent_skill_host
        index = await AgentSkill.resolve_index(self.agent_skill_ids)
        self._agent_skill_host = AgentSkillRuntimeHost(
            attached_ids=frozenset(self.agent_skill_ids),
            index_entries=tuple(index),
        )
        return self._agent_skill_host

    async def _ensure_agent_skill_meta_tools(self, tools: list[BaseTool]) -> list[BaseTool]:
        if not self.agent_skill_ids:
            return tools
        known = {tool.name for tool in tools}
        merged = list(tools)
        for meta_tool in (load_agent_skill, read_agent_skill_reference):
            if meta_tool.name in known:
                continue
            known.add(meta_tool.name)
            merged.append(meta_tool)
        return merged

    def _is_data_table_resource_ref(self, ref: ResourceReferenceInput) -> bool:
        if isinstance(ref, ResourceReference):
            return ref.type == ResourceType.DATA_TABLE
        raw_type = ref.get("type")
        return raw_type == ResourceType.DATA_TABLE.value

    async def _has_data_table_resource(self, state: ExecutionState | None) -> bool:
        node_resources = _config_resource_refs(self.config)
        for ref in node_resources.values():
            if self._is_data_table_resource_ref(ref):
                return True
        if self._node_config is not None:
            for ref in (self._node_config.resources or {}).values():
                if self._is_data_table_resource_ref(ref):
                    return True
        if state is None:
            return False
        flow_resources, skill_resources = await self.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        for mapping in (flow_resources, skill_resources):
            if mapping is None:
                continue
            for ref in mapping.values():
                if self._is_data_table_resource_ref(ref):
                    return True
        return False

    async def _ensure_data_table_tools(
        self,
        tools: list[BaseTool],
        state: ExecutionState | None,
    ) -> list[BaseTool]:
        if not await self._has_data_table_resource(state):
            return tools
        known = {tool.name for tool in tools}
        merged = list(tools)
        for table_tool in TABLES_TOOLS:
            if table_tool.name in known:
                continue
            known.add(table_tool.name)
            merged.append(table_tool)
        return merged

    async def set_tools(self, tools: list[BaseTool]) -> None:
        """Устанавливает tools."""
        self._loaded_tools = tools

    def _create_llm_client(self, state: ExecutionState | None = None):
        """Возвращает company-aware LLM client для direct node вызовов.

        Основной runtime создаёт client внутри runner-а из той же effective config,
        чтобы биллинг и фактический вызов использовали один источник истины.
        """
        base = self._node_config or self._create_default_config()
        effective = resolve_effective_llm_config_for_node(base)
        logger.info(
            "flows.create_llm_client.node_id.provider.model.source",
            node_id=self.node_id,
            provider=effective.config.provider,
            model=effective.config.model,
            source=effective.source,
        )
        return create_llm_client_from_call_config(
            effective.config,
            billing_service=self.billing_service,
            variables=state.variables if state is not None else None,
            fallback_models=effective.config.fallback_models,
        )

    async def _resolve_effective_node_config(
        self, base: NodeConfig, state: ExecutionState | None
    ) -> NodeConfig:
        llm_config = base.llm
        if not llm_config:
            return base
        explicit = llm_config.llm_resource_key and str(llm_config.llm_resource_key).strip()
        if state is None:
            if explicit:
                raise ValueError("ExecutionState is required when llm_resource_key is set")
            return base
        flow_resources, skill_resources = await self.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        node_resources_raw = _config_resource_refs(self.config)
        if explicit:
            merged_ov = await resolve_llm_config_with_resource_key(
                llm_config=llm_config,
                flow_resources=flow_resources or {},
                skill_resources=skill_resources,
                node_resources_raw=node_resources_raw,
            )
            return base.model_copy(update={"llm": merged_ov})
        inferred = await infer_unique_llm_resource_key_from_merged_maps(
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
        )
        if inferred is None:
            return base
        ov_with_key = llm_config.model_copy(update={"llm_resource_key": inferred})
        merged_ov = await resolve_llm_config_with_resource_key(
            llm_config=ov_with_key,
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
        )
        return base.model_copy(update={"llm": merged_ov})

    async def _resolve_effective_llm_context_policy(
        self,
        base: NodeConfig,
        state: ExecutionState | None,
    ) -> LLMContextProfile:
        node_resources_raw: dict[str, ResourceReferenceInput] = dict(base.resources or {})
        if not node_resources_raw:
            node_resources_raw = _config_resource_refs(self.config)
        explicit = bool(
            base.llm_context_resource_key and str(base.llm_context_resource_key).strip()
        )
        has_node_resources = bool(node_resources_raw)
        if state is None:
            if explicit or has_node_resources:
                raise ValueError("ExecutionState is required for LLM context resources")
            return await resolve_llm_context_policy_for_runtime(
                llm_context_resource_key=None,
                flow_resources={},
                skill_resources=None,
                node_resources_raw={},
                node=base.llm_context,
            )

        if not explicit and not has_node_resources:
            return await resolve_llm_context_policy_for_runtime(
                llm_context_resource_key=None,
                flow_resources={},
                skill_resources=None,
                node_resources_raw={},
                node=base.llm_context,
            )

        flow_resources, skill_resources = await self.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        return await resolve_llm_context_policy_for_runtime(
            llm_context_resource_key=base.llm_context_resource_key,
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            node=base.llm_context,
        )

    async def _resolve_llm_context_source_registry(
        self,
        base: NodeConfig,
        state: ExecutionState | None,
        policy: LLMContextProfile,
    ) -> LLMContextSourceRegistry | None:
        if policy.mode == "off" or policy.retrieval.mode == "off":
            return None

        node_resources_raw: dict[str, ResourceReferenceInput] = dict(base.resources or {})
        if not node_resources_raw:
            node_resources_raw = _config_resource_refs(self.config)
        has_node_resources = bool(node_resources_raw)
        if state is None:
            if has_node_resources:
                raise ValueError("ExecutionState is required for LLM context RAG resources")
            return None

        flow_resources, skill_resources = await self.flow_factory.get_resource_maps(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        sources: list[LLMContextSource] = []
        memory_source = resolve_memory_context_source_for_runtime(
            store=self.llm_context_memory_store,
            state=state,
            node_id=self.node_id,
        )
        if memory_source is not None:
            sources.append(memory_source)

        rag_registry = await resolve_rag_context_source_registry_for_runtime(
            flow_resources=flow_resources or {},
            skill_resources=skill_resources,
            node_resources_raw=node_resources_raw,
            namespace_service=self.namespace_service,
            state=state,
            authz=self.authz_service,
        )
        if rag_registry is not None:
            sources.extend(rag_registry.sources)
        if not sources:
            return None
        return LLMContextSourceRegistry(sources)

    def _create_default_config(self) -> NodeConfig:
        """Создает конфигурацию по умолчанию."""
        llm_config = None
        if self.llm_config_dict:
            allowed = set(NodeLLMConfig.model_fields.keys())
            raw_llm = {k: v for k, v in self.llm_config_dict.items() if k in allowed}
            llm_config = NodeLLMConfig.model_validate(raw_llm)

        react_config = None
        react_dict = _config_mapping(self.config, "react")
        if react_dict:
            react_config = ReactConfig.model_validate(react_dict)

        structured_output = _config_bool(self.config, "structured_output", False)
        output_schema = _config_json_object(self.config, "output_schema")
        messages_filter = _config_messages_filter(self.config, "messages_filter")
        llm_context = None
        llm_context_raw = self.config.get("llm_context") if self.config else None
        if llm_context_raw is not None:
            llm_context = LLMContextPatch.model_validate(llm_context_raw)
        llm_context_resource_key = _config_optional_string(
            self.config,
            "llm_context_resource_key",
        )

        exc_response = False
        exc_allow: list[ExceptionAbsorbAllowName] = []
        llm_capability: LLMCapability | None = None
        if self.config:
            if "exception_as_response" in self.config:
                exc_response = bool(self.config["exception_as_response"])
            raw_allow = self.config.get("exception_allow_types")
            if raw_allow is not None:
                if not isinstance(raw_allow, list):
                    raise ValueError("exception_allow_types: expected list[str]")
                exc_allow = [ExceptionAbsorbAllowName(str(item)) for item in raw_allow]
            raw_capability = self.config.get("llm_capability")
            if raw_capability is not None:
                if not isinstance(raw_capability, str):
                    raise ValueError(
                        f"llm_capability: expected one of {sorted(LLM_CAPABILITY_VALUES)}, got {raw_capability!r}"
                    )
                match raw_capability:
                    case (
                        "llm_chat"
                        | "llm_summarize"
                        | "llm_format_markdown"
                        | "llm_codegen"
                        | "llm_vision"
                        | "image_gen"
                    ):
                        llm_capability = raw_capability
                    case _:
                        raise ValueError(
                            f"llm_capability: expected one of {sorted(LLM_CAPABILITY_VALUES)}, got {raw_capability!r}"
                        )
        resources = {
            key: ResourceReference.model_validate(value)
            for key, value in _config_resource_refs(self.config).items()
        }

        return NodeConfig(
            node_id=self.node_id,
            type=NodeType.LLM_NODE,
            name=self.node_id,
            description=self.description or "",
            prompt=self.prompt_template or self.prompt or "",
            llm=llm_config,
            llm_context=llm_context,
            llm_context_resource_key=llm_context_resource_key,
            llm_capability=llm_capability,
            resources=resources,
            react=react_config,
            structured_output=structured_output,
            output_schema=output_schema,
            messages_filter=messages_filter,
            exception_as_response=exc_response,
            exception_allow_types=exc_allow,
        )

    async def _load_tools(self, state: ExecutionState | None = None) -> list[BaseTool]:
        """
        Создаёт tools из inline конфигов.

        Code tools execute in isolated runners. Platform access goes through
        capability-gateway, so resources are not injected into tool namespaces.
        """
        _ = state
        return await self.tool_registry.create_tools(self.tool_refs)

    async def before_prompt_render(
        self, prompt_template: str, state: ExecutionState, variables: JsonObject
    ) -> tuple[str, JsonObject]:
        """
        Хук вызывается ДО рендеринга промпта.
        Переопределите для модификации промпта и переменных.

        Аргументы:
            prompt_template: Исходный шаблон промпта
            state: Текущее state
            variables: Переменные для рендеринга

        Возвращает:
            (modified_prompt_template, modified_variables)
        """
        _ = state
        return prompt_template, variables

    async def after_prompt_render(self, rendered_prompt: str, state: ExecutionState) -> str:
        """
        Хук вызывается ПОСЛЕ рендеринга промпта.
        Переопределите для модификации финального промпта.

        Аргументы:
            rendered_prompt: Рендеренный промпт
            state: Текущий state

        Возвращает:
            Модифицированный промпт
        """
        _ = state
        return rendered_prompt


class CodeNode(BaseNode):
    """
    Универсальная нода для выполнения кода.

    Поддерживает языки python, javascript, typescript, go, csharp.
    Только function-entrypoint через runner.execute_tool(code, args, state) по строке ``code`` из конфига;
    ``tool_id`` — идентификатор для UI/ссылок, не путь к FunctionTool в процессе.
    """

    node_type: ClassVar[NodeType | None] = NodeType.CODE

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        cfg = self.config

        self.language: str = _config_string(cfg, "language", "python")
        raw_entrypoint = cfg.get("entrypoint")
        self.entrypoint: str | None = (
            raw_entrypoint.strip()
            if isinstance(raw_entrypoint, str) and raw_entrypoint.strip()
            else None
        )
        raw_code = cfg.get("code")
        self.code: str | None = raw_code if isinstance(raw_code, str) else None
        raw_tool_id = cfg.get("tool_id")
        self.tool_id: str | None = raw_tool_id if isinstance(raw_tool_id, str) else None
        self.parameters_schema: JsonObject | None = _config_parameters_schema(cfg)

    def _get_runner(self):
        """Возвращает isolated runner для текущего языка."""
        return self.execution.code_runners.runner(self.language)

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Выполняет только inline ``code`` через runner.execute_tool(code, args, state).
        """
        code = self.code
        if code is None or code.strip() == "":
            raise ValueError(
                f"Node '{self.node_id}': non-empty inline code is required (tool_id without code is not executed)"
            )
        if self.config.get("resources"):
            raise ValueError(
                f"Code node '{self.node_id}': resources are not injected into sandbox code. "
                + "Use tools.<tool_id>(...) / tools.call('<tool_id>', ...) from the sandbox SDK or a dedicated platform capability."
            )
        args = self._build_args(inputs)
        logger.info("flows.node.tool_execute", node_id=self.node_id, arg_keys=list(args.keys()))

        runner = self._get_runner()
        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "language": self.language,
                "entrypoint": self.entrypoint,
                "code": code,
                "args": args,
                "state_hash": self._state_hash_for_activity(state),
            },
            "code_node.activity_input",
        )

        async def invoke() -> NodeRunResult:
            return await runner.execute_tool(
                code,
                args,
                state,
                entrypoint=self.entrypoint,
            )

        return await self._run_durable_activity(
            state,
            activity_type="code",
            input_payload=input_payload,
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
        )

    def _build_args(self, inputs: NodeInputs) -> JsonObject:
        """Формирует args из inputs с учетом defaults из parameters_schema."""
        args: JsonObject = {}

        if self.parameters_schema:
            properties = require_json_object(
                self.parameters_schema.get("properties", {}),
                "parameters_schema.properties",
            )
            for name, schema in properties.items():
                if isinstance(schema, Mapping) and "default" in schema:
                    args[name] = schema["default"]

        args.update(inputs)
        return args


class FlowNode(BaseNode):
    """Вложенный Flow как отдельная durable child workflow."""

    node_type: ClassVar[NodeType | None] = NodeType.FLOW

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        flow_factory: FlowFactoryProtocol,
        tool_registry: ToolRegistryProtocol,
        handoff_orchestrator_service: HandoffOrchestratorService,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.flow_factory: FlowFactoryProtocol = flow_factory
        self.tool_registry: ToolRegistryProtocol = tool_registry
        self.handoff_orchestrator_service: HandoffOrchestratorService = handoff_orchestrator_service
        cfg = self.config
        r_f = cfg.get("flow_id")
        if isinstance(r_f, str) and r_f.strip():
            self.flow_id: str | None = r_f
        else:
            self.flow_id = None
        r_s = cfg.get("branch_id")
        if isinstance(r_s, str) and r_s.strip():
            self.branch_id: str = r_s
        else:
            self.branch_id = "default"
        raw_call_type = cfg.get("call_type", NodeToolCallType.CALL.value)
        self.call_type: NodeToolCallType = NodeToolCallType(raw_call_type)
        self.is_handoff: bool = self.call_type == NodeToolCallType.HANDOFF
        self._nested_flow: RuntimeFlowProtocol | None = None

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """
        Запускает вложенный Flow как child workflow.

        Parent ledger хранит ChildWorkflow* events, а сам child имеет отдельный
        session_id и собственную event history. State child не копируется в
        parent snapshots; parent хранит только typed link для resume.

        При call_type=handoff родитель suspended сразу после запуска child
        и ждёт handback (а не обычного child completion).
        """
        if not self.flow_id:
            raise ValueError(f"Node '{self.node_id}': flow_id required")

        nested_flow = await self._load_nested_flow()
        existing_link = self._resume_link_from_parent_state(state)

        if self.is_handoff and existing_link is not None and existing_link.handoff:
            if existing_link.status == "completed":
                nested_state, link, _child_started = await self._load_child_workflow_state(
                    state,
                    existing_link,
                )
                self._copy_child_result_to_parent(nested_state, state, link)
                await self._record_child_workflow_event(
                    state.session_id,
                    WorkflowEventType.child_workflow_completed,
                    link,
                )
                return state.response

        if existing_link is None:
            nested_state, link, _child_started = await self._create_child_workflow_state(
                state,
                inputs,
                nested_flow,
            )
        else:
            nested_state, link, _child_started = await self._load_child_workflow_state(
                state,
                existing_link,
            )

        if self.is_handoff:
            link = link.model_copy(update={"handoff": True})
            state.child_workflows[self.node_id] = link

        await self._record_child_workflow_event(
            state.session_id,
            WorkflowEventType.child_workflow_started,
            link,
        )

        if link.status == "completed":
            self._copy_child_result_to_parent(nested_state, state, link)
            await self._record_child_workflow_event(
                state.session_id,
                WorkflowEventType.child_workflow_completed,
                link,
            )
            return state.response

        if link.status == "suspended" and not state.content:
            self._copy_child_result_to_parent(nested_state, state, link)
            self._attach_child_resume_path(state, link)
            await self._record_child_workflow_event(
                state.session_id,
                WorkflowEventType.child_workflow_suspended,
                link,
            )
            return state.response

        try:
            result = await nested_flow.run(nested_state)
        except Exception as exc:
            failed_link = link.model_copy(update={"status": "failed"})
            state.child_workflows[self.node_id] = failed_link
            await self._record_child_workflow_event(
                state.session_id,
                WorkflowEventType.child_workflow_failed,
                failed_link,
                error=str(exc),
            )
            raise

        next_status = "suspended" if result.interrupt or result.breakpoint_hit else "completed"
        next_link = link.model_copy(update={"status": next_status})
        self._copy_child_result_to_parent(result, state, next_link)

        if result.interrupt or result.breakpoint_hit:
            self._attach_child_resume_path(state, next_link)
            await self._record_child_workflow_event(
                state.session_id,
                WorkflowEventType.child_workflow_suspended,
                next_link,
            )
        else:
            state.interrupt_path = []
            await self._record_child_workflow_event(
                state.session_id,
                WorkflowEventType.child_workflow_completed,
                next_link,
            )

        return state.response

    def _required_flow_id(self) -> str:
        if self.flow_id is None:
            raise ValueError(f"Node '{self.node_id}': flow_id required")
        return self.flow_id

    async def _load_nested_flow(self) -> RuntimeFlowProtocol:
        flow_id = self._required_flow_id()
        if self._nested_flow is None:
            self._nested_flow = await self.flow_factory.get_flow(
                flow_id,
                self.branch_id,
                tool_registry=self.tool_registry,
            )
        nested_flow = self._nested_flow
        if nested_flow is None:
            raise ValueError(f"Flow node '{self.node_id}': nested flow '{flow_id}' not found")
        return nested_flow

    def _require_parent_child_scope(self, state: ExecutionState) -> tuple[str, int]:
        execution_branch_id = state.durable_execution_branch_id
        if execution_branch_id is None:
            raise RuntimeError(f"Flow node '{self.node_id}' requires durable execution_branch_id")
        node_schedule_sequence = state.durable_node_schedule_sequence
        if node_schedule_sequence is None:
            raise RuntimeError(f"Flow node '{self.node_id}' requires NodeScheduled.sequence")
        return execution_branch_id, node_schedule_sequence

    def _child_context_id(
        self,
        state: ExecutionState,
        inputs: NodeInputs,
        *,
        parent_execution_branch_id: str,
        parent_node_schedule_sequence: int,
    ) -> str:
        flow_id = self._required_flow_id()
        scope_hash = hash_state_json(
            {
                "parent_session_id": state.session_id,
                "parent_execution_branch_id": parent_execution_branch_id,
                "parent_node_id": self.node_id,
                "parent_node_schedule_sequence": parent_node_schedule_sequence,
                "child_flow_id": flow_id,
                "child_flow_branch_id": self.branch_id,
                "inputs": inputs,
            }
        )
        return (
            f"{state.context_id}:child:{self.node_id}:"
            + f"{parent_execution_branch_id}:{parent_node_schedule_sequence}:"
            + scope_hash[:16]
        )

    @staticmethod
    def _child_config_version(nested_flow: RuntimeFlowProtocol) -> str | None:
        raw_version = nested_flow.config.get("version")
        return str(raw_version) if raw_version is not None else None

    async def _require_child_execution_position(
        self,
        child_session_id: str,
    ) -> WorkflowExecutionPosition:
        position = await self.execution.active_position(child_session_id)
        if position is None:
            raise RuntimeError(
                "Child workflow durable position not found: " + f"{child_session_id!r}"
            )
        return position

    async def _child_status_from_durable_state(
        self,
        child_state: ExecutionState,
    ) -> ChildWorkflowStatus:
        if child_state.interrupt is not None or child_state.breakpoint_hit is not None:
            return "suspended"
        if child_state.current_nodes:
            return "running"

        offset = 0
        limit = 200
        while True:
            history, total = await self.execution.state_history(
                child_state.session_id,
                limit=limit,
                offset=offset,
            )
            for event in history:
                payload = event.payload
                if (
                    event.event_type is WorkflowEventType.superstep_committed
                    and isinstance(payload, SuperstepCommittedPayload)
                    and not payload.next_nodes
                ):
                    return "completed"
            if not history or offset + len(history) >= total:
                return "running"
            offset += len(history)

    def _copy_child_result_to_parent(
        self,
        child_state: ExecutionState,
        parent_state: ExecutionState,
        link: ChildWorkflowLink,
    ) -> None:
        preserved_links = dict(parent_state.child_workflows)
        preserved_links[self.node_id] = link
        self._copy_state_back(child_state, parent_state, full_trust=False)
        parent_state.child_workflows = preserved_links

    async def _create_child_workflow_state(
        self,
        parent_state: ExecutionState,
        inputs: NodeInputs,
        nested_flow: RuntimeFlowProtocol,
    ) -> tuple[ExecutionState, ChildWorkflowLink, bool]:
        flow_id = self._required_flow_id()
        parent_execution_branch_id, parent_node_schedule_sequence = (
            self._require_parent_child_scope(parent_state)
        )
        if self.is_handoff:
            child_context_id, child_session_id = (
                self.handoff_orchestrator_service.build_child_session_ids(
                    parent_state.context_id,
                    flow_id,
                )
            )
        else:
            child_context_id = self._child_context_id(
                parent_state,
                inputs,
                parent_execution_branch_id=parent_execution_branch_id,
                parent_node_schedule_sequence=parent_node_schedule_sequence,
            )
            child_session_id = f"{flow_id}:{child_context_id}"
        existing_child = await self.execution.get_state(child_session_id)
        if existing_child is not None:
            child_position = await self._require_child_execution_position(
                child_session_id,
            )
            link = ChildWorkflowLink(
                node_id=self.node_id,
                child_session_id=child_session_id,
                child_flow_id=flow_id,
                child_flow_branch_id=self.branch_id,
                child_execution_branch_id=child_position.execution_branch_id,
                parent_session_id=parent_state.session_id,
                parent_execution_branch_id=parent_execution_branch_id,
                parent_node_schedule_sequence=parent_node_schedule_sequence,
                status=await self._child_status_from_durable_state(
                    existing_child,
                ),
                handoff=self.is_handoff,
            )
            return existing_child, link, False

        child_state = ExecutionState.model_validate(
            parent_state.model_dump(mode="python", exclude_none=False)
        )
        for key, value in inputs.items():
            child_state[key] = value
        child_state.session_id = child_session_id
        child_state.context_id = child_context_id
        # Child workflow has its own A2A projection scope (session/context/flow).
        child_state.task_id = str(uuid.uuid4())
        child_state.branch_id = self.branch_id
        child_state.flow_config_version = self._child_config_version(nested_flow)
        child_state.current_nodes = []
        child_state.node_history = {}
        child_state.join_arrived_preds = {}
        child_state.child_workflows = {}
        child_state.terminal_task_state = None
        child_state.terminal_task_error = None
        child_state.response = None
        child_state.result = None
        child_state.validation = None
        child_state.messages = self.get_filtered_messages(parent_state)

        if self.is_handoff:
            child_state.handoff_parent_session_id = parent_state.session_id
            child_state.handoff_depth = parent_state.handoff_depth + 1
            if parent_state.handoff_trace_id is not None:
                child_state.handoff_trace_id = parent_state.handoff_trace_id

        run_started = await self.execution.record_state(
            child_session_id,
            child_state,
            event_type=WorkflowEventType.run_started,
            payload=RunStartedPayload(
                parent_session_id=parent_state.session_id,
                parent_node_id=self.node_id,
                parent_execution_branch_id=parent_execution_branch_id,
                parent_node_schedule_sequence=parent_node_schedule_sequence,
                child_flow_id=flow_id,
                child_flow_branch_id=self.branch_id,
            ),
            snapshot=True,
        )
        child_execution_branch_id = run_started.execution_branch_id
        if not child_execution_branch_id:
            raise RuntimeError("Child workflow RunStarted did not return execution_branch_id")
        link = ChildWorkflowLink(
            node_id=self.node_id,
            child_session_id=child_session_id,
            child_flow_id=flow_id,
            child_flow_branch_id=self.branch_id,
            child_execution_branch_id=child_execution_branch_id,
            parent_session_id=parent_state.session_id,
            parent_execution_branch_id=parent_execution_branch_id,
            parent_node_schedule_sequence=parent_node_schedule_sequence,
            status="running",
            handoff=self.is_handoff,
        )
        return child_state, link, True

    async def _load_child_workflow_state(
        self,
        parent_state: ExecutionState,
        link: ChildWorkflowLink,
    ) -> tuple[ExecutionState, ChildWorkflowLink, bool]:
        child_state = await self.execution.get_state(link.child_session_id)
        if child_state is None:
            raise RuntimeError(
                "Child workflow link points to missing durable session: "
                + f"{link.child_session_id!r}"
            )
        child_position = await self._require_child_execution_position(
            link.child_session_id,
        )
        if child_position.execution_branch_id != link.child_execution_branch_id:
            raise RuntimeError(
                "Child workflow active execution branch does not match parent link: "
                + f"child_session_id={link.child_session_id!r}"
            )
        if link.status == "completed":
            return child_state, link, False
        if parent_state.content:
            child_state.content = parent_state.content
        if parent_state.interrupt_path:
            child_state.interrupt_path = list(parent_state.interrupt_path[1:])
        return child_state, link.model_copy(update={"status": "running"}), False

    def _resume_link_from_parent_state(self, state: ExecutionState) -> ChildWorkflowLink | None:
        if state.interrupt_path:
            first = state.interrupt_path[0]
            if (
                first.node_type == NodeType.FLOW.value
                and first.node_id == self.node_id
                and first.child_session_id is not None
                and first.child_flow_id is not None
                and first.child_flow_branch_id is not None
                and first.child_execution_branch_id is not None
            ):
                existing = state.child_workflows.get(self.node_id)
                if existing is not None and existing.child_session_id == first.child_session_id:
                    return existing
                parent_execution_branch_id, parent_node_schedule_sequence = (
                    self._require_parent_child_scope(state)
                )
                return ChildWorkflowLink(
                    node_id=self.node_id,
                    child_session_id=first.child_session_id,
                    child_flow_id=first.child_flow_id,
                    child_flow_branch_id=first.child_flow_branch_id,
                    child_execution_branch_id=first.child_execution_branch_id,
                    parent_session_id=state.session_id,
                    parent_execution_branch_id=parent_execution_branch_id,
                    parent_node_schedule_sequence=parent_node_schedule_sequence,
                    status="running",
                )
        existing_link = state.child_workflows.get(self.node_id)
        if existing_link is None:
            return None
        if existing_link.status in {"running", "suspended", "completed"}:
            return existing_link
        return None

    def _attach_child_resume_path(
        self,
        state: ExecutionState,
        link: ChildWorkflowLink,
    ) -> None:
        child_item = InterruptPathItem(
            node_type=NodeType.FLOW.value,
            node_id=self.node_id,
            child_session_id=link.child_session_id,
            child_flow_id=link.child_flow_id,
            child_flow_branch_id=link.child_flow_branch_id,
            child_execution_branch_id=link.child_execution_branch_id,
        )
        state.interrupt_path = [child_item, *state.interrupt_path]
        if state.interrupt is not None:
            system = state.interrupt.system.model_copy(
                update={
                    "path": [item.model_dump(mode="json") for item in state.interrupt_path],
                    "task_id": state.task_id,
                    "context_id": state.context_id,
                }
            )
            state.interrupt = state.interrupt.model_copy(update={"system": system})

    async def _record_child_workflow_event(
        self,
        parent_session_id: str,
        event_type: WorkflowEventType,
        link: ChildWorkflowLink,
        *,
        error: str | None = None,
    ) -> None:
        if await self._child_workflow_event_exists(
            parent_session_id=parent_session_id,
            event_type=event_type,
            link=link,
        ):
            logger.info(
                "child_workflow.lifecycle_event_replayed",
                parent_session_id=parent_session_id,
                child_session_id=link.child_session_id,
                child_execution_branch_id=link.child_execution_branch_id,
                event_type=event_type.value,
                node_id=self.node_id,
            )
            return
        child_position = await self._require_child_execution_position(
            link.child_session_id,
        )
        if child_position.execution_branch_id != link.child_execution_branch_id:
            raise RuntimeError(
                "Child workflow lifecycle event branch mismatch: "
                + f"child_session_id={link.child_session_id!r}"
            )
        payload = ChildWorkflowLifecyclePayload(
            node_id=self.node_id,
            child_session_id=link.child_session_id,
            child_flow_id=link.child_flow_id,
            child_flow_branch_id=link.child_flow_branch_id,
            child_execution_branch_id=link.child_execution_branch_id,
            parent_execution_branch_id=link.parent_execution_branch_id,
            parent_node_schedule_sequence=link.parent_node_schedule_sequence,
            child_execution_position=child_position,
            status=link.status,
            error=error,
        )
        _ = await self.execution.record_lifecycle(
            parent_session_id,
            event_type=event_type,
            payload=payload,
        )

    async def _child_workflow_event_exists(
        self,
        *,
        parent_session_id: str,
        event_type: WorkflowEventType,
        link: ChildWorkflowLink,
    ) -> bool:
        offset = 0
        limit = 200
        while True:
            history, total = await self.execution.state_history(
                parent_session_id,
                limit=limit,
                offset=offset,
            )
            for event in history:
                payload = event.payload
                if (
                    event.event_type is event_type
                    and isinstance(payload, ChildWorkflowLifecyclePayload)
                    and payload.node_id == self.node_id
                    and payload.child_session_id == link.child_session_id
                    and payload.child_execution_branch_id == link.child_execution_branch_id
                    and payload.parent_execution_branch_id == link.parent_execution_branch_id
                    and payload.parent_node_schedule_sequence == link.parent_node_schedule_sequence
                ):
                    return True
            if not history or offset + len(history) >= total:
                return False
            offset += len(history)


class RemoteFlowNode(BaseNode):
    """Внешний flow по A2A протоколу (только direct URL, без registry flow_id)."""

    node_type: ClassVar[NodeType | None] = NodeType.REMOTE_FLOW

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        a2a_client: A2AClient,
        emitter_factory: EmitterFactory,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.a2a_client: A2AClient = a2a_client
        self.emitter_factory: EmitterFactory = emitter_factory
        cfg = self.config

        self.url: str | None = _config_optional_string(cfg, "url")
        self.branch_id: str = _config_string(cfg, "branch_id", "default")
        self.headers_config: dict[str, str] = _config_string_map_default(cfg, "headers")
        self.metadata_template: str = _config_string(cfg, "metadata_template", "{}")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает внешний flow по A2A."""
        url_raw = self.url
        if not isinstance(url_raw, str) or not url_raw.strip():
            raise ValueError("RemoteFlowNode requires non-empty 'url'")

        variables = state.variables
        url = MappingResolver.resolve_http_header_value(url_raw, state, variables)
        req_headers = self._resolve_headers_dict(self.headers_config, state, variables)
        metadata = require_json_object(
            MappingResolver.parse_and_resolve_body_template(
                self.metadata_template,
                state,
                variables,
            ),
            "remote_flow.metadata_template",
        )

        content = inputs.get("content", state.content or "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "url": url,
                "content": content,
                "session_id": state.session_id,
                "branch_id": self.branch_id,
                "headers": req_headers,
                "metadata": metadata,
            },
            "remote_flow.activity_input",
        )

        activity_id = (
            f"{state.session_id}:{state.durable_execution_branch_id or ''}:"
            f"{self.node_id}:remote_flow"
        )

        async def invoke() -> NodeRunResult:
            context = get_request_context()
            if context is None or context.active_company is None:
                raise ValueError("RemoteFlowNode requires Context with active_company")
            a2a_task_id = str(uuid.uuid4())
            row = await submit_a2a_call(
                a2a_client=self.a2a_client,
                service="flows",
                company_id=context.active_company.company_id,
                user_id=context.user.user_id,
                base_url=url,
                content=content,
                context_id=state.session_id,
                branch_id=self.branch_id,
                a2a_task_id=a2a_task_id,
                continuation=TASK_FLOWS_REMOTE_TASK_FINISHED,
                continuation_kwargs={
                    "session_id": state.session_id,
                    "flow_id": state.session_flow_id,
                    "branch_id": state.branch_id,
                    "task_id": state.task_id,
                    "context_id": state.context_id,
                    "node_id": self.node_id,
                    "activity_id": activity_id,
                    "user_id": context.user.user_id,
                    "context_data": context.to_dict(),
                },
                deadline_seconds=float(get_flows_settings().default_flow_timeout_seconds),
                metadata=metadata,
                headers=req_headers,
                parent_task_id=state.task_id,
            )
            raise RemoteTaskParked(
                activity_id=activity_id,
                a2a_task_id=row.a2a_task_id,
                node_id=self.node_id,
                base_url=url,
            )

        remote_result = await self._run_durable_activity(
            state,
            activity_type="remote_flow",
            input_payload=input_payload,
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
            activity_id=activity_id,
            idempotency_key=activity_id,
        )
        remote = require_json_object(remote_result, "remote_flow.result")
        status = remote.get("status")
        if status != "completed":
            error = remote.get("error")
            detail = error if isinstance(error, str) and error else "unknown"
            raise A2AClientError(f"Remote A2A task ended with status {status!r}: {detail}")
        response_value = remote.get("response")
        state.response = response_value if isinstance(response_value, str) else ""
        state["remote_status"] = status
        artifacts_value = remote.get("artifacts")
        artifacts = artifacts_value if isinstance(artifacts_value, list) else []
        state["remote_artifacts"] = artifacts

        emitter = await self.emitter_factory.create(state)
        for artifact_payload in artifacts:
            remote_artifact = artifact_from_json_dict(
                require_json_object(artifact_payload, "remote_flow.artifact")
            )
            # Parent task may already own the remote's artifact_id (e.g. "response")
            # from a prior remote hop or local stream — scope into this node.
            scoped_artifact = Artifact()
            scoped_artifact.CopyFrom(remote_artifact)
            remote_artifact_id = remote_artifact.artifact_id.strip()
            if remote_artifact_id == "":
                raise ValueError("remote artifact.artifact_id is required")
            scoped_artifact.artifact_id = f"remote:{self.node_id}:{remote_artifact_id}"
            await emitter.emit_exact_artifact(scoped_artifact, last_chunk=True)

        return state.response

    def _resolve_headers_dict(
        self,
        headers: dict[str, str] | None,
        state: ExecutionState,
        variables: JsonObject,
    ) -> dict[str, str]:
        if not headers:
            return {}
        return {
            k: MappingResolver.resolve_http_header_value(v, state, variables)
            for k, v in headers.items()
        }


def _put_code_agent_env(
    target: dict[str, str],
    key: str,
    value: str,
    *,
    source: str,
) -> None:
    if not guest_env_key_is_valid(key):
        raise ValueError(f"{source} key {key!r} is not a valid env name")
    if guest_env_key_is_reserved(key):
        raise ValueError(f"{source} key {key!r} is reserved for the platform")
    if value.strip() == "":
        raise ValueError(f"{source} {key} resolved to an empty string")
    if key in target:
        raise ValueError(f"{source} overlaps guest_env key {key}")
    target[key] = value


def _merge_code_agent_env(*, mapped: dict[str, str], inputs: NodeInputs) -> dict[str, str]:
    merged = dict(mapped)
    bag = inputs.get("env")
    if bag is not None:
        env_bag = require_json_object(bag, "code_agent.input_mapping.env")
        for env_key, raw_value in env_bag.items():
            _put_code_agent_env(
                merged,
                env_key,
                MappingResolver.stringify_mapping_value(raw_value),
                source="input_mapping.env",
            )
    for key, raw_value in inputs.items():
        if key in {"content", "env"}:
            continue
        if not guest_env_key_is_valid(key):
            continue
        _put_code_agent_env(
            merged,
            key,
            MappingResolver.stringify_mapping_value(raw_value),
            source="input_mapping",
        )
    return validate_guest_env(merged)


def _code_agent_metadata_from_inputs(inputs: NodeInputs) -> JsonObject:
    extra: JsonObject = {}
    for key, value in inputs.items():
        if key in {"content", "env"}:
            continue
        if guest_env_key_is_valid(key):
            continue
        extra[key] = require_json_value(value, f"code_agent.input_mapping.{key}")
    return extra


def _merge_code_agent_metadata(template: JsonObject, extra: JsonObject) -> JsonObject:
    overlap = set(template).intersection(extra)
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise ValueError(f"code_agent metadata_template overlaps input_mapping keys: {joined}")
    merged = dict(template)
    merged.update(extra)
    return merged


def _code_agent_state_from_artifact(artifact_payload: JsonObject) -> JsonObject:
    parts = artifact_payload.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("code_agent state artifact parts required")
    part = require_json_object(parts[0], "code_agent.state.parts[0]")
    data = part.get("data")
    return require_json_object(data, "code_agent.state.data")


class CodeAgentNode(BaseNode):
    """Агент из дерева исходников Documents + контейнер на ферме guest_runtime."""

    node_type: ClassVar[NodeType | None] = NodeType.CODE_AGENT

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        a2a_client: A2AClient,
        emitter_factory: EmitterFactory,
        code_agent_source_service: CodeAgentSourceService,
        guest_runtime_client: GuestRuntimeClient,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.a2a_client: A2AClient = a2a_client
        self.emitter_factory: EmitterFactory = emitter_factory
        self.code_agent_source_service: CodeAgentSourceService = code_agent_source_service
        self.guest_runtime_client: GuestRuntimeClient = guest_runtime_client
        cfg = self.config
        self.catalog_id: str | None = _config_optional_string(cfg, "catalog_id")
        language_raw = _config_optional_string(cfg, "language")
        self.language: str | None = language_raw
        invoke_kind_raw = _config_optional_string(cfg, "invoke_kind")
        self.invoke_kind: str | None = invoke_kind_raw
        self.invoke_argv: list[str] = _config_string_list(cfg, "invoke_argv")
        self.invoke_listen_port: int | None = _config_optional_int(cfg, "invoke_listen_port")
        self.egress_hosts: list[str] = _config_string_list(cfg, "egress_hosts")
        self.idle_ttl_seconds: int | None = _config_optional_int(cfg, "idle_ttl_seconds")
        self.guest_env: dict[str, str] = _config_string_map_default(cfg, "guest_env")
        self.metadata_template: str = _config_string(cfg, "metadata_template", "{}")

    def _platform_env(
        self,
        *,
        execution_token: str,
        llm_url: str,
        gateway_url: str,
        state: ExecutionState,
        company_id: str,
        context_channel: str,
        request_id: str,
        trace_id: str,
        namespace: str | None,
    ) -> dict[str, str]:
        platform: dict[str, str] = {
            "OPENAI_API_KEY": execution_token,
            "OPENAI_BASE_URL": llm_url,
            "CAPABILITY_GATEWAY_URL": gateway_url,
            "PLATFORM_EXECUTION_TOKEN": execution_token,
            "PLATFORM_SESSION_ID": state.session_id,
            "PLATFORM_TASK_ID": state.task_id,
            "PLATFORM_CONTEXT_ID": state.context_id,
            "PLATFORM_FLOW_ID": state.session_flow_id,
            "PLATFORM_NODE_ID": self.node_id,
            "PLATFORM_COMPANY_ID": company_id,
            "PLATFORM_BRANCH_ID": state.branch_id,
            "PLATFORM_CHANNEL": context_channel,
            "PLATFORM_SOURCE_NODE_ID": self.node_id,
            "PLATFORM_REQUEST_ID": request_id,
            "PLATFORM_TRACE_ID": trace_id,
            "PLATFORM_USER_ID": state.user_id,
        }
        if namespace is not None:
            platform["PLATFORM_NAMESPACE"] = namespace
        test_scope = resolve_test_scope()
        if test_scope is not None:
            platform["PLATFORM_TEST_SCOPE"] = test_scope
        return platform

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        catalog_id = self.catalog_id
        if catalog_id is None or not catalog_id.strip():
            raise ValueError(f"CodeAgentNode {self.node_id}: catalog_id is required")
        if not self.invoke_argv:
            raise ValueError(f"CodeAgentNode {self.node_id}: invoke_argv is required")
        language = self.language
        if language is None:
            raise ValueError(f"CodeAgentNode {self.node_id}: language is required")
        invoke_kind = self.invoke_kind
        if invoke_kind is None:
            raise ValueError(f"CodeAgentNode {self.node_id}: invoke_kind is required")

        content_value = inputs.get("content")
        if content_value is None:
            content_value = state.content
        if isinstance(content_value, str):
            content = content_value
        elif content_value is None:
            raise ValueError(f"CodeAgentNode {self.node_id}: content is required")
        else:
            content = json.dumps(content_value, ensure_ascii=False)

        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "catalog_id": catalog_id,
                "language": language,
                "invoke_kind": invoke_kind,
                "invoke_argv": list(self.invoke_argv),
                "content": content,
                "session_id": state.session_id,
            },
            "code_agent.activity_input",
        )

        activity_id = (
            f"{state.session_id}:{state.durable_execution_branch_id or ''}:"
            f"{self.node_id}:code_agent"
        )

        async def invoke() -> NodeRunResult:
            context = get_request_context()
            (
                company_id,
                user_id,
                namespace,
                request_id,
                trace_id,
                claims,
            ) = self._code_agent_runtime_identity(state)
            execution_token = issue_execution_token(claims)
            files = await self.code_agent_source_service.list_files(catalog_id=catalog_id)
            settings = get_settings()
            llm_url = f"{settings.server.get_service_url('flows').rstrip('/')}/flows/api/v1/llm/v1"
            gateway_url = settings.server.get_service_url("capability_gateway").rstrip("/")
            platform_env = self._platform_env(
                execution_token=execution_token,
                llm_url=llm_url,
                gateway_url=gateway_url,
                state=state,
                company_id=company_id,
                context_channel=context.channel if context else "",
                request_id=request_id,
                trace_id=trace_id,
                namespace=namespace,
            )
            guest_env = _merge_code_agent_env(
                mapped=MappingResolver.resolve_env_mapping(
                    self.guest_env,
                    state,
                    platform=platform_env,
                ),
                inputs=inputs,
            )
            metadata = _merge_code_agent_metadata(
                require_json_object(
                    MappingResolver.parse_and_resolve_body_template(
                        self.metadata_template,
                        state,
                        state.variables,
                    ),
                    "code_agent.metadata_template",
                ),
                _code_agent_metadata_from_inputs(inputs),
            )
            lease = await self.guest_runtime_client.ensure_lease(
                GuestEnsureLeaseRequest(
                    flow_id=state.session_flow_id,
                    node_id=self.node_id,
                    company_id=company_id,
                    user_id=user_id,
                    catalog_id=catalog_id,
                    language=GuestLanguage(language),
                    invoke_kind=GuestInvokeKind(invoke_kind),
                    invoke_argv=list(self.invoke_argv),
                    invoke_listen_port=self.invoke_listen_port,
                    egress_hosts=list(self.egress_hosts),
                    files=files,
                    execution_token=execution_token,
                    llm_proxy_base_url=llm_url,
                    capability_gateway_base_url=gateway_url,
                    session_id=state.session_id,
                    task_id=state.task_id,
                    context_id=state.context_id,
                    branch_id=state.branch_id,
                    channel=context.channel if context else "",
                    source_node_id=self.node_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    namespace=namespace,
                    durable_execution_branch_id=state.durable_execution_branch_id,
                    durable_node_schedule_sequence=state.durable_node_schedule_sequence,
                    durable_superstep_sequence=state.durable_superstep_sequence,
                    idle_ttl_seconds=self.idle_ttl_seconds,
                    guest_env=guest_env,
                )
            )
            row = await submit_a2a_call(
                a2a_client=self.a2a_client,
                service="flows",
                company_id=company_id,
                user_id=user_id,
                base_url=lease.a2a_url,
                content=content,
                context_id=state.session_id,
                branch_id=state.branch_id,
                continuation=TASK_FLOWS_REMOTE_TASK_FINISHED,
                continuation_kwargs={
                    "session_id": state.session_id,
                    "flow_id": state.session_flow_id,
                    "branch_id": state.branch_id,
                    "task_id": state.task_id,
                    "context_id": state.context_id,
                    "node_id": self.node_id,
                    "activity_id": activity_id,
                    "user_id": user_id,
                    "context_data": context.to_dict() if context else {},
                },
                deadline_seconds=float(get_flows_settings().default_flow_timeout_seconds),
                metadata=metadata or None,
                parent_task_id=state.task_id,
            )
            raise RemoteTaskParked(
                activity_id=activity_id,
                a2a_task_id=row.a2a_task_id,
                node_id=self.node_id,
                base_url=lease.a2a_url,
            )

        remote_result = await self._run_durable_activity(
            state,
            activity_type="code_agent",
            input_payload=input_payload,
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
            activity_id=activity_id,
            idempotency_key=activity_id,
        )
        remote = require_json_object(remote_result, "code_agent.result")
        status = remote.get("status")
        if status != "completed":
            error = remote.get("error")
            detail = error if isinstance(error, str) and error else "unknown"
            raise A2AClientError(
                f"Code agent A2A task ended with status {status!r}: {detail}"
            )
        response_value = remote.get("response")
        response_text = response_value if isinstance(response_value, str) else ""
        state.response = response_text
        state["code_agent_status"] = status
        artifacts_value = remote.get("artifacts")
        result_artifacts = artifacts_value if isinstance(artifacts_value, list) else []
        state["code_agent_artifacts"] = result_artifacts

        context = get_request_context()
        (
            company_id,
            user_id,
            namespace,
            request_id,
            trace_id,
            claims,
        ) = self._code_agent_runtime_identity(state)
        execution_token = issue_execution_token(claims)

        emitter = await self.emitter_factory.create(state)
        effect_envelopes: list[PlatformEffectEnvelope] = []
        interrupt_payload: JsonObject | None = None
        guest_state: JsonObject = {}
        for artifact_payload in result_artifacts:
            artifact_dict = require_json_object(
                artifact_payload, "code_agent.artifact"
            )
            remote_artifact = artifact_from_json_dict(artifact_dict)
            remote_artifact_id = remote_artifact.artifact_id.strip()
            if remote_artifact_id == "":
                raise ValueError("code_agent artifact.artifact_id is required")
            if remote_artifact_id == "platform_effects":
                effect_envelopes.extend(
                    _platform_effects_from_artifact(artifact_dict)
                )
            elif remote_artifact_id == "interrupt":
                interrupt_payload = _interrupt_from_artifact(artifact_dict)
            elif remote_artifact_id == "state":
                guest_state = _code_agent_state_from_artifact(artifact_dict)
            scoped_artifact = Artifact()
            scoped_artifact.CopyFrom(remote_artifact)
            scoped_artifact.artifact_id = (
                f"code_agent:{self.node_id}:{remote_artifact_id}"
            )
            await emitter.emit_exact_artifact(scoped_artifact, last_chunk=True)

        if effect_envelopes:
            execution_context = CapabilityExecutionContext(
                execution_token=execution_token,
                company_id=company_id,
                user_id=user_id,
                flow_id=state.session_flow_id,
                branch_id=state.branch_id,
                session_id=state.session_id,
                task_id=state.task_id,
                context_id=state.context_id,
                channel=context.channel if context else "",
                request_id=request_id,
                trace_id=trace_id,
                durable_execution_branch_id=state.durable_execution_branch_id,
                durable_node_schedule_sequence=state.durable_node_schedule_sequence,
                durable_superstep_sequence=state.durable_superstep_sequence,
                source_node_id=self.node_id,
                namespace=namespace,
            )
            apply_capability_platform_effects(
                state,
                effect_envelopes,
                context=execution_context,
                manifest=await load_sandbox_capability_manifest(),
                interface=current_flow_interface(),
            )
        if interrupt_payload is not None:
            body = parse_interrupt_body_from_external_dict(interrupt_payload)
            InterruptManager.apply_interrupt(state, body, tool_call=None)
            return None
        node_result: JsonObject = dict(guest_state)
        if "response" not in node_result:
            node_result["response"] = response_text
        return node_result

    def _code_agent_runtime_identity(
        self,
        state: ExecutionState,
    ) -> tuple[str, str, str | None, str, str, CapabilityExecutionTokenClaims]:
        """(company, user, namespace, request_id, trace_id, claims) для token/lease/effects."""
        context = get_request_context()
        if context is None or context.active_company is None:
            raise ValueError("CodeAgentNode requires Context with active_company")
        log_context = get_log_context()
        request_id = log_context.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("CodeAgentNode requires request_id")
        trace_id = context.trace_id
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("CodeAgentNode requires trace_id")
        company_id = context.active_company.company_id
        user_id = context.user.user_id
        if not user_id.strip():
            raise ValueError("CodeAgentNode requires user_id")
        namespace_raw = context.active_namespace
        if not namespace_raw.strip() or namespace_raw.strip() == "default":
            namespace = None
        else:
            namespace = namespace_raw.strip()
        claims = CapabilityExecutionTokenClaims(
            company_id=company_id,
            user_id=user_id,
            flow_id=state.session_flow_id,
            branch_id=state.branch_id,
            session_id=state.session_id,
            task_id=state.task_id,
            context_id=state.context_id,
            channel=context.channel,
            request_id=request_id,
            durable_execution_branch_id=state.durable_execution_branch_id,
            durable_node_schedule_sequence=state.durable_node_schedule_sequence,
            durable_superstep_sequence=state.durable_superstep_sequence,
            source_node_id=self.node_id,
            namespace=namespace,
            test_scope=resolve_test_scope(),
            exp=execution_token_exp(
                get_flows_settings().capability_execution_token_ttl_seconds
            ),
        )
        return company_id, user_id, namespace, request_id, trace_id, claims


def _platform_effects_from_artifact(artifact_payload: JsonObject) -> list[PlatformEffectEnvelope]:
    parts = artifact_payload.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("code_agent platform_effects artifact parts required")
    envelopes: list[PlatformEffectEnvelope] = []
    for index, raw_part in enumerate(parts):
        part = require_json_object(raw_part, f"code_agent.platform_effects.parts[{index}]")
        data = part.get("data")
        if not isinstance(data, list):
            raise ValueError("code_agent platform_effects data must be a list")
        for item in data:
            envelopes.append(PlatformEffectEnvelope.model_validate(item))
    return envelopes


def _interrupt_from_artifact(artifact_payload: JsonObject) -> JsonObject:
    parts = artifact_payload.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("code_agent interrupt artifact parts required")
    part = require_json_object(parts[0], "code_agent.interrupt.parts[0]")
    data = part.get("data")
    return require_json_object(data, "code_agent.interrupt.data")


class ExternalAPINode(BaseNode):
    """Вызов внешнего HTTP API."""

    node_type: ClassVar[NodeType | None] = NodeType.EXTERNAL_API

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.api_config: JsonObject = self.config

    def _build_api_config(self) -> ExternalAPIConfig:
        """Строит конфиг API."""
        raw_url = self.api_config.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError(f"ExternalAPINode {self.node_id}: url is required")
        return ExternalAPIConfig(
            api_id=self.node_id,
            name=_config_string(self.api_config, "name", self.node_id),
            description=_config_optional_string(self.api_config, "description"),
            url=raw_url,
            method=HTTPMethod(_config_string(self.api_config, "method", HTTPMethod.POST.value)),
            headers=_config_string_map_default(self.api_config, "headers"),
            timeout=_config_float(self.api_config, "timeout", 30.0),
            body_template=_config_string(self.api_config, "body_template", "{}"),
            state_mapping=_config_string_map_default(self.api_config, "state_mapping"),
        )

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает внешний API с inputs как аргументами."""
        api_cfg = self._build_api_config()
        variables = state.variables

        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "api": api_cfg.model_dump(mode="json"),
                "inputs": inputs,
                "variables": variables,
                "state_hash": self._state_hash_for_activity(state),
            },
            "external_api.activity_input",
        )

        async def invoke() -> NodeRunResult:
            client = ExternalAPIClient(timeout=api_cfg.timeout)
            result = require_json_object(
                await client.call(api_cfg, inputs, variables, state),
                "external_api.response",
            )

            if result.get("status") == "waiting_input" and result.get("interrupt"):
                interrupt_data = result["interrupt"]
                if not isinstance(interrupt_data, dict):
                    raise ValueError(
                        "ExternalAPINode: interrupt must be a dict, "
                        + f"got {type(interrupt_data)}"
                    )
                body = parse_interrupt_body_from_external_dict(
                    require_json_object(interrupt_data, "external_api.interrupt"),
                )
                InterruptManager.apply_interrupt(state, body, tool_call=None)
                return None

            if result.get("status") == "error":
                err = result.get("error")
                if err is None:
                    raise ValueError("ExternalAPINode: status=error without an 'error' field")
                raise ValueError(f"External API error: {err}")

            for response_field, state_field in api_cfg.state_mapping.items():
                data = result.get("data", {})
                if isinstance(data, dict) and response_field in data:
                    state[state_field] = data[response_field]

            data = result.get("data")
            state["api_response"] = data
            state["api_status"] = result.get("status")
            state["result"] = data

            return data

        return await self._run_durable_activity(
            state,
            activity_type="external_api",
            input_payload=input_payload,
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
        )


class MCPNode(BaseNode):
    """
    Вызов MCP tool как нода графа.

    Подключается к MCP серверу и вызывает указанный tool.
    """

    node_type: ClassVar[NodeType | None] = NodeType.MCP

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        variables_service: VariablesService,
        flow_access_service: FlowAccessService,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.variables_service: VariablesService = variables_service
        self.flow_access_service: FlowAccessService = flow_access_service
        cfg = self.config

        self.server_id: str | None = _config_optional_string(cfg, "server_id")
        self.tool_name: str | None = _config_optional_string(cfg, "tool_name")
        self.extra_headers: dict[str, str] = _config_string_map_default(cfg, "headers")
        self.state_mapping: dict[str, str] = _config_string_map_default(cfg, "state_mapping")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Вызывает MCP tool."""
        if not self.server_id:
            raise ValueError(f"MCPNode '{self.node_id}': server_id is required")
        if not self.tool_name:
            raise ValueError(f"MCPNode '{self.node_id}': tool_name is required")
        server_id = self.server_id
        tool_name = self.tool_name

        server = await MCPServerConfig.get(
            MCPServerConfig.server_row_id_for_active_company(server_id)
        )
        if not server:
            raise ValueError(f"MCP server not found: {server_id}")

        request_headers = {**server.headers, **self.extra_headers}
        request_server = server.model_copy(update={"headers": request_headers})

        tool_id = mcp_tool_reference_id(server_id, tool_name)
        tool_ref = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
        if tool_ref is None:
            logger.info(
                "flows.mcpnode.syncing.missing.toolreference", node_id=self.node_id, tool_id=tool_id
            )
            try:
                _tool_ids, _tools = await sync_mcp_server_tools(
                    variables_service=self.variables_service,
                    flow_access_service=self.flow_access_service,
                    server_config=server,
                )
            except Exception as exc:
                raise ValueError(
                    f"MCPNode '{self.node_id}' could not sync ToolReference '{tool_id}': {exc}"
                ) from exc
            tool_ref = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
            if tool_ref is None:
                raise ValueError(
                    f"MCPNode '{self.node_id}' requires synced ToolReference '{tool_id}'"
                )
        mcp_contract = tool_ref.require_mcp_contract()

        variables = require_json_object(state.variables, "state.variables")
        headers_hash = hash_state_json(require_json_object(request_headers, "mcp.request_headers"))
        variables_hash = hash_state_json(variables)

        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "server_id": server_id,
                "tool_name": tool_name,
                "tool_id": tool_id,
                "schema_hash": mcp_contract.schema_hash,
                "schema_version": mcp_contract.schema_version,
                "inputs": inputs,
                "headers_hash": headers_hash,
                "variables_hash": variables_hash,
                "state_hash": self._state_hash_for_activity(state),
            },
            "mcp.activity_input",
        )

        async def invoke() -> NodeRunResult:
            client = MCPClient(request_server, variables)
            _ = await client.require_tool_contract(
                tool_name,
                expected_schema_hash=mcp_contract.schema_hash,
                expected_schema_version=mcp_contract.schema_version,
            )
            result = await client.call_tool(tool_name, inputs)

            if result.is_error:
                raise ValueError(f"MCP tool error: {result.get_text()}")

            node_result: JsonValue = (
                result.structured_content
                if result.structured_content is not None
                else result.get_text()
            )

            for _field, state_field in self.state_mapping.items():
                state[state_field] = node_result

            state["mcp_result"] = node_result

            return node_result

        return await self._run_durable_activity(
            state,
            activity_type="mcp",
            input_payload=input_payload,
            side_effect_policy=_mcp_side_effect_policy(mcp_contract.annotations),
            invoke=invoke,
        )


class DatasourceNode(BaseNode):
    """Шаг графа: introspect/query/execute к DatasourceConnection."""

    node_type: ClassVar[NodeType | None] = NodeType.DATASOURCE

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        datasource_service: DatasourceService,
        datasource_executors: DatasourceExecutors,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.datasource_service: DatasourceService = datasource_service
        self.datasource_executors: DatasourceExecutors = datasource_executors
        cfg = self.config
        self.connector_id: str | None = _config_optional_string(cfg, "connector_id")
        self.datasource_id: str | None = _config_optional_string(cfg, "datasource_id")
        raw_operation = cfg.get("datasource_operation")
        if not isinstance(raw_operation, str) or not raw_operation.strip():
            raise ValueError(f"DatasourceNode '{self.node_id}': datasource_operation is required")
        self.datasource_operation: DatasourceOperation = DatasourceOperation(raw_operation)
        self.sql: str | None = _config_optional_string(cfg, "sql")
        self.state_mapping: dict[str, str] = _config_string_map_default(cfg, "state_mapping")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        if self.connector_id is None or not self.connector_id.strip():
            raise ValueError(f"DatasourceNode '{self.node_id}': connector_id is required")
        if self.datasource_id is None or not self.datasource_id.strip():
            raise ValueError(f"DatasourceNode '{self.node_id}': datasource_id is required")
        datasource_id = self.datasource_id
        operation = self.datasource_operation
        sql = self.sql
        params = inputs
        service = self.datasource_service
        executors = self.datasource_executors
        variables = require_json_object(state.variables, "state.variables")
        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "connector_id": self.connector_id,
                "datasource_id": datasource_id,
                "datasource_operation": operation.value,
                "sql": sql,
                "inputs": inputs,
                "variables_hash": hash_state_json(variables),
                "state_hash": self._state_hash_for_activity(state),
            },
            "datasource.activity_input",
        )

        async def invoke() -> NodeRunResult:
            if operation is DatasourceOperation.INTROSPECT:
                protocol_result = await service.introspect(datasource_id, executors=executors)
            elif operation is DatasourceOperation.QUERY:
                if sql is None or not sql.strip():
                    raise ValueError(f"DatasourceNode '{self.node_id}': sql is required for query")
                protocol_result = await service.query(
                    datasource_id, sql, params, executors=executors
                )
            elif operation is DatasourceOperation.EXECUTE:
                if sql is None or not sql.strip():
                    raise ValueError(
                        f"DatasourceNode '{self.node_id}': sql is required for execute"
                    )
                protocol_result = await service.execute(
                    datasource_id, sql, params, executors=executors
                )
            else:
                raise ValueError(
                    f"DatasourceNode '{self.node_id}': unsupported operation {operation}"
                )
            dumped = require_json_object(
                protocol_result.model_dump(mode="json"),
                "datasource.protocol_result",
            )
            for _field, state_field in self.state_mapping.items():
                state[state_field] = dumped
            state["datasource_result"] = dumped
            state["result"] = dumped
            return dumped

        side_effect = (
            SideEffectPolicy.non_idempotent
            if operation is DatasourceOperation.EXECUTE
            else SideEffectPolicy.idempotent
        )
        return await self._run_durable_activity(
            state,
            activity_type="datasource",
            input_payload=input_payload,
            side_effect_policy=side_effect,
            invoke=invoke,
        )


class ChannelNode(BaseNode):
    """
    Универсальная нода отправки сообщений в каналы.

    Поддерживаемые каналы: telegram, email, webhook, sms.

    Конфигурация:
    {
        "type": "channel",
        "channel": "telegram",
        "action": "send_message",
        "channel_config": {
            "bot_token": "@var:my_bot_token",
            "parse_mode": "HTML"
        },
        "input_mapping": {
            "recipient": "@state:triggers.my_telegram.context.chat_id",
            "text": "@state:response"
        }
    }

    Поддерживаемые actions:
    - send_message: текстовое сообщение
    - send_photo: фото с подписью
    - send_document: документ/файл
    - send_payload: произвольный JSON (для webhook)
    - send_notification: A2A Protocol 1.0 StreamResponse statusUpdate (webhook push)
    """

    node_type: ClassVar[NodeType | None] = NodeType.CHANNEL

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        channel_registry: ChannelRegistryProtocol,
        mail_service: MailService,
    ):
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.channel_registry: ChannelRegistryProtocol = channel_registry
        self.mail_service: MailService = mail_service
        cfg = self.config

        channel_value = cfg.get("channel")
        if not isinstance(channel_value, str) or not channel_value.strip():
            raise ValueError("channel: required non-empty string")
        self.channel: ChannelType = ChannelType(channel_value.strip())
        action_value = cfg.get("action")
        if not isinstance(action_value, str) or not action_value.strip():
            raise ValueError("action: required non-empty string")
        self.action: str = action_value.strip()
        self.channel_config: JsonObject = _config_mapping_default(cfg, "channel_config")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        """Отправляет сообщение через channel handler."""
        handler = self.channel_registry.get(
            self.channel,
            mail_service=self.mail_service,
        )

        # Собираем все переменные (flow, компании, системные)
        all_variables = require_json_object(
            VariableResolver.resolve_all(local_vars=state.variables),
            "channel.all_variables",
        )

        # Слияние channel_config с inputs
        config = {**self.channel_config}
        config = VarResolver.resolve_deep(config, all_variables)
        params = inputs
        variables = all_variables

        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "channel": self.channel.value,
                "action": self.action,
                "params": params,
                "config": config,
                "variables": variables,
                "state_hash": self._state_hash_for_activity(state),
            },
            "channel.activity_input",
        )

        async def invoke() -> NodeRunResult:
            async with traced_operation(
                "flows.channel.execute_action",
                event_type="channel.action",
                operation_category="channel",
                extra_attributes={
                    "platform.channel.type": self.channel.value,
                    "platform.channel.action": self.action,
                },
            ):
                result = await handler.execute_action(
                    action=self.action,
                    params=params,
                    config=config,
                    variables=variables,
                    state=state,
                )

            state["channel_result"] = result
            state["result"] = result

            logger.info(
                "flows.node.channel_complete",
                node_id=self.node_id,
                channel=self.channel.value,
                action=self.action,
            )

            return result

        return await self._run_durable_activity(
            state,
            activity_type="channel",
            input_payload=input_payload,
            side_effect_policy=SideEffectPolicy.non_idempotent,
            invoke=invoke,
        )


class HitlNode(BaseNode):
    """
    Нода передачи диалога оператору очереди (персистентная задача + interrupt).
    После complete в очереди: resume с тем же correlation — задача в БД completed,
    нода выставляет response и отдаёт управление следующим нодам по рёбрам.
    """

    node_type: ClassVar[NodeType | None] = NodeType.HITL_NODE

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        hitl_work_item_service: HitlWorkItemService,
        hitl_conversation_service: HitlConversationService,
    ) -> None:
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.hitl_work_item_service: HitlWorkItemService = hitl_work_item_service
        self.hitl_conversation_service: HitlConversationService = hitl_conversation_service

    def _hitl_local_variables(self) -> JsonObject | None:
        raw = self.config.get("local_variables")
        if raw is None:
            return None
        return require_json_object(raw, f"hitl_node.{self.node_id}.local_variables")

    def _resolve_hitl_text(self, template: str, state: ExecutionState) -> str:
        raw = template.strip()
        if not raw:
            raise ValueError(f"hitl_node {self.node_id}: empty title/message template")
        return MappingResolver.resolve_interpolated_string(
            raw,
            state,
            variables=self._hitl_local_variables(),
        )

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        ctx = get_request_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError(f"hitl_node {self.node_id}: Context with active_company is required")
        company_id = ctx.active_company.company_id
        cid_resume = state.hitl_handoff_correlation_id
        if isinstance(cid_resume, str) and cid_resume.strip():
            existing_resume = await WorkItem.any_by_correlation_id(company_id, cid_resume.strip())
            if existing_resume is None:
                raise ValueError(
                    f"hitl_node {self.node_id}: resume with correlation_id={cid_resume!r}, "
                    + "operator task not found"
                )
            if existing_resume.state != WorkItemState.DONE:
                raise ValueError(
                    f"hitl_node {self.node_id}: operator task is not completed yet "
                    + f"(state={existing_resume.state.value!r})"
                )
            snapshot = self._hitl_snapshot_from_work_item(existing_resume)
            state.hitl_handoff_correlation_id = None
            answer = str(state.content).strip()
            state.response = answer
            # Closing reply уже в Redis (operator_reply); completed не должен дублировать текст в UI.
            state.hitl_streamed_closing_text = answer
            _ = await self.execution.record_lifecycle(
                state.session_id,
                event_type=WorkflowEventType.handoff_resumed,
                payload=HandoffResumedPayload(
                    current_nodes=[self.node_id],
                    node_id=self.node_id,
                    handoff_command_id=snapshot.handoff_command_id,
                    correlation_id=cid_resume.strip(),
                    work_item_id=existing_resume.work_item_id,
                    response_preview=answer[:HANDOFF_PREVIEW_MAX_LEN],
                ),
            )
            logger.info(
                "hitl.work_item.resumed",
                work_item_id=existing_resume.work_item_id,
                correlation_id=cid_resume.strip(),
                handoff_command_id=snapshot.handoff_command_id,
                session_id=state.session_id,
                node_id=self.node_id,
            )
            return None

        slug_in = inputs.get("assignee_queue")
        slug_cfg = self.config.get("work_queue_slug")

        slug_effective: str
        if isinstance(slug_in, str) and slug_in.strip():
            slug_effective = slug_in.strip()
        elif isinstance(slug_cfg, str) and slug_cfg.strip():
            slug_effective = slug_cfg.strip()
        else:
            raise ValueError(
                f"hitl_node {self.node_id}: specify work_queue_slug "
                + "or input_mapping.assignee_queue"
            )

        title_raw = inputs.get("task_title") or self.config.get("handoff_task_title")
        if not title_raw or not str(title_raw).strip():
            raise ValueError(
                f"hitl_node {self.node_id}: task_title is required (input_mapping or handoff_task_title)"
            )
        message_raw = (
            inputs.get("user_facing_message")
            or inputs.get("question")
            or self.config.get("handoff_user_message")
        )
        if not message_raw or not str(message_raw).strip():
            raise ValueError(
                f"hitl_node {self.node_id}: user-facing text is required "
                + "(user_facing_message / question / handoff_user_message)"
            )

        raw_mode = inputs.get("handoff_mode") or self.config.get("handoff_mode") or "single_reply"
        mode = HandoffMode(str(raw_mode).strip())

        svc = self.hitl_work_item_service
        task_title = self._resolve_hitl_text(str(title_raw), state)
        question = self._resolve_hitl_text(str(message_raw), state)
        if not task_title:
            raise ValueError(f"hitl_node {self.node_id}: task_title is empty after resolve")
        if not question:
            raise ValueError(f"hitl_node {self.node_id}: user message is empty after resolve")
        handoff_command = build_hitl_handoff_command(
            state=state,
            node_id=self.node_id,
        )
        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "company_id": company_id,
                "handoff_command_id": handoff_command.idempotency_key,
                "correlation_id": str(handoff_command.correlation_id),
                "execution_branch_id": handoff_command.execution_branch_id,
                "node_schedule_sequence": handoff_command.node_schedule_sequence,
                "question": question,
                "task_title": task_title,
                "assignee_queue_slug": slug_effective,
                "handoff_mode": mode.value,
                "state_hash": self._state_hash_for_activity(state),
            },
            "hitl_handoff.activity_input",
        )

        async def invoke() -> NodeRunResult:
            cid, work_item_id = await svc.register_handoff(
                state,
                question=question,
                task_title=task_title,
                assignee_queue_slug=slug_effective,
                handoff_mode=mode,
                command=handoff_command,
            )
            await self.hitl_conversation_service.materialize_triggering_user_content(
                company_id=company_id,
                work_item_id=work_item_id,
                state=state,
                node_id=self.node_id,
            )
            return {
                "correlation_id": str(cid),
                "work_item_id": work_item_id,
                "handoff_command_id": handoff_command.idempotency_key,
                "execution_branch_id": handoff_command.execution_branch_id,
                "node_schedule_sequence": handoff_command.node_schedule_sequence,
            }

        handoff = require_json_object(
            await self._run_durable_activity(
                state,
                activity_type="hitl_handoff",
                input_payload=input_payload,
                side_effect_policy=SideEffectPolicy.idempotent,
                activity_id=handoff_command.idempotency_key,
                idempotency_key=handoff_command.idempotency_key,
                invoke=invoke,
            ),
            "hitl_handoff.result",
        )
        correlation_id = handoff.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id:
            raise ValueError("hitl_handoff.result.correlation_id: required string")
        work_item_id_raw = handoff.get("work_item_id")
        work_item_id = work_item_id_raw if isinstance(work_item_id_raw, str) else None
        raise FlowInterrupt(
            body=OperatorTaskInterrupt(
                question=question,
                task_title=task_title,
                assignee_queue=slug_effective,
                handoff_mode=mode,
                work_item_id=work_item_id,
                handoff_command_id=handoff_command.idempotency_key,
                execution_branch_id=handoff_command.execution_branch_id,
                node_schedule_sequence=handoff_command.node_schedule_sequence,
                node_id=self.node_id,
                tool_call_id=None,
            ),
            correlation_id=uuid.UUID(correlation_id),
        )

    @staticmethod
    def _hitl_snapshot_from_work_item(work_item: WorkItem) -> HitlInterruptSnapshot:
        for hook in work_item.hooks:
            snapshot_raw = hook.binding.get("interrupt_snapshot")
            if isinstance(snapshot_raw, dict):
                return HitlInterruptSnapshot.model_validate(snapshot_raw)
        raise ValueError(
            f"WorkItem {work_item.work_item_id!r} without interrupt_snapshot in hook.binding"
        )


class ReflectionNode(BaseNode):
    """Типизированный critic / test-time compute gate без записи state внутри activity."""

    name: ClassVar[str] = "reflection"
    node_type: ClassVar[NodeType | None] = NodeType.REFLECTION

    def __init__(
        self,
        node_id: str,
        config: JsonObject | None = None,
        *,
        execution: FlowExecutionContext,
        redis_client: RedisClient,
        billing_service: BillingService,
    ) -> None:
        super().__init__(node_id, config, execution=execution, redis_client=redis_client)
        self.billing_service: BillingService = billing_service
        policy_payload = _config_mapping(self.config, "critic_policy")
        if policy_payload is None:
            raise ValueError(f"reflection node {self.node_id}: critic_policy is required")
        self.critic_policy: CriticPolicy = CriticPolicy.model_validate(policy_payload)

        llm_payload = _config_mapping(self.config, "llm")
        if llm_payload is None:
            raise ValueError(f"reflection node {self.node_id}: llm is required")
        self.llm_config: NodeLLMConfig = NodeLLMConfig.model_validate(llm_payload)
        if self.llm_config.model is None:
            raise ValueError(f"reflection node {self.node_id}: llm.model is required")
        if self.llm_config.fallback_models:
            raise ValueError(f"reflection node {self.node_id}: fallback_models are not allowed")

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        target_snapshot = self._resolve_target_snapshot(state)
        result = await self._run_reflection_activity(
            state=state,
            target_snapshot=target_snapshot,
        )
        execution_branch_id = state.durable_execution_branch_id
        if execution_branch_id is None:
            raise RuntimeError("reflection result requires durable execution_branch_id")
        node_schedule_sequence = state.durable_node_schedule_sequence
        if node_schedule_sequence is None:
            raise RuntimeError("reflection result requires NodeScheduled.sequence")

        record = ReflectionRecord(
            node_id=self.node_id,
            execution_branch_id=execution_branch_id,
            node_schedule_sequence=node_schedule_sequence,
            result=result,
        )
        state.reflection_history.append(record)
        state.validation = require_json_object(
            result.model_dump(mode="json"),
            "reflection.validation",
        )
        self._present_reflection_result(state, result)
        logger.info(
            "reflection.gate_completed",
            node_id=self.node_id,
            policy_id=result.policy_id,
            gate=result.gate,
            approved=result.approved,
            exit_id=result.exit_id,
            session_id=state.session_id,
            execution_branch_id=execution_branch_id,
        )
        return None

    def _present_reflection_result(
        self,
        state: ExecutionState,
        result: ReflectionGateResult,
    ) -> None:
        exit_label = result.exit_id
        for exit_item in self.critic_policy.exits:
            if exit_item.exit_id == result.exit_id:
                exit_label = exit_item.label
                break
        lines = [f"**{exit_label}** — {result.critique.decision}", result.critique.summary]
        for issue in result.critique.issues[:5]:
            lines.append(f"- {issue.severity}: {issue.finding}")
        for reason in result.blocked_reasons:
            lines.append(f"- {reason}")
        _ = show_reflection(
            state,
            card_id=card_block_id("reflection", f"{self.node_id}-{result.exit_id}"),
            text="\n".join(line for line in lines if line.strip() != ""),
        )

    def _resolve_target_snapshot(self, state: ExecutionState) -> ReflectionTargetSnapshot:
        target = self.critic_policy.target
        if target.kind == "response":
            value: ExecutionStateValue | None = state.response
        elif target.kind == "result":
            value = state.result
        elif target.kind == "validation":
            value = state.validation
        else:
            path = target.state_path
            if path is None:
                raise ValueError("reflection target state_path is required")
            value = MappingResolver.get_nested_value(state, path)

        if value is None:
            raise ValueError(f"reflection target {target.kind!r} is empty")
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"reflection target {target.kind!r} is empty")
        return ReflectionTargetSnapshot(
            target=target,
            value=require_json_value(value, f"reflection.target.{target.kind}"),
        )

    async def _run_reflection_activity(
        self,
        *,
        state: ExecutionState,
        target_snapshot: ReflectionTargetSnapshot,
    ) -> ReflectionGateResult:
        input_payload = require_json_object(
            {
                "node_id": self.node_id,
                "policy": self.critic_policy.model_dump(mode="json"),
                "target_snapshot": target_snapshot.model_dump(mode="json"),
            },
            "reflection.activity_input",
        )
        activity_id = self._durable_activity_id(state, "reflection", input_payload)
        completed = await self.execution.activities.schedule(
            session_id=state.session_id,
            activity_id=activity_id,
            activity_type="reflection",
            input_payload=input_payload,
            node_id=self.node_id,
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.idempotent,
        )
        if completed is not None:
            return self._reflection_result_from_completed(completed)

        started = await self.execution.activities.start(activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark reflection activity as started: {activity_id!r}")

        try:
            async with traced_operation(
                "flows.reflection.critique",
                event_type="reflection.critique",
                operation_category="reflection",
                extra_attributes={
                    ATTR_NODE_ID: self.node_id,
                    ATTR_REFLECTION_POLICY_ID: self.critic_policy.policy_id,
                    ATTR_REFLECTION_GATE: self.critic_policy.gate,
                    ATTR_REFLECTION_TARGET: self.critic_policy.target.kind,
                },
            ):
                critique = await self._invoke_critic_llm(
                    input_payload=input_payload,
                    target_snapshot=target_snapshot,
                    state=state,
                )
                result = evaluate_reflection_gate(
                    policy=self.critic_policy,
                    critique=critique,
                )
        except Exception as exc:
            completed_failed = await self.execution.activities.complete(
                activity_id=activity_id,
                error=str(exc),
            )
            if not completed_failed:
                raise RuntimeError(
                    f"Failed to mark reflection activity as failed: {activity_id!r}"
                ) from exc
            raise

        completed_ok = await self.execution.activities.complete(
            activity_id=activity_id,
            result_json={
                "result": result.model_dump(mode="json"),
            },
        )
        if not completed_ok:
            raise RuntimeError(f"Failed to mark reflection activity as completed: {activity_id!r}")
        return result

    @staticmethod
    def _reflection_result_from_completed(completed: JsonObject) -> ReflectionGateResult:
        if "result" not in completed:
            raise ValueError("reflection activity result missing result")
        result_raw = completed["result"]
        if not isinstance(result_raw, dict):
            raise ValueError("reflection activity result must be an object")
        return ReflectionGateResult.model_validate(result_raw)

    async def _invoke_critic_llm(
        self,
        *,
        input_payload: JsonObject,
        target_snapshot: ReflectionTargetSnapshot,
        state: ExecutionState,
    ) -> ReflectionCritiqueResult:
        llm_cfg = self.llm_config
        llm = create_llm_client_from_call_config(
            llm_cfg,
            billing_service=self.billing_service,
            variables=state.variables,
            fallback_models=llm_cfg.fallback_models,
            allow_platform_paid_fallback=False,
        )
        message_id = "reflection-" + hash_state_json(input_payload)
        prompt = self._critic_prompt(target_snapshot)
        message = Message(
            message_id=message_id,
            role=ROLE_USER,
            parts=[Part(text=prompt)],
            metadata=struct_from_mapping(
                {
                    "node_id": self.node_id,
                    "reflection_policy_id": self.critic_policy.policy_id,
                }
            ),
            task_id=state.task_id,
            context_id=state.context_id,
        )
        result = await llm.chat(
            [message],
            response_model=ReflectionCritiqueResult,
            llm_context={"profile": "off"},
        )
        return result

    def _critic_prompt(self, target_snapshot: ReflectionTargetSnapshot) -> str:
        policy_json = json.dumps(
            self.critic_policy.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        target_json = json.dumps(
            target_snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        return "\n".join(
            (
                "You are a strict critic gate for an agent workflow.",
                "Evaluate only the provided target against the policy.",
                "Do not propose or execute side effects.",
                "Return only structured JSON matching the response schema.",
                "",
                "[Critic policy]",
                policy_json,
                "",
                "[Target snapshot]",
                target_json,
            )
        )


class ResourceNode(BaseNode):
    """
    Нода-ресурс на графе: позиция на канве и привязка записей resources у ноды.
    Рантайм не вызывает LLM и не мутирует state. LLM resource islands используются
    только при сборке LLM-конфига; sandbox code не получает resources как namespace.
    """

    name: ClassVar[str] = "resource"
    node_type: ClassVar[NodeType | None] = NodeType.RESOURCE

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> None:
        _ = state
        _ = inputs
        return None


RUNTIME_NODE_CLASSES: Mapping[NodeType, type[BaseNode]] = {
    NodeType.LLM_NODE: LlmNode,
    NodeType.CODE: CodeNode,
    NodeType.FLOW: FlowNode,
    NodeType.REMOTE_FLOW: RemoteFlowNode,
    NodeType.CODE_AGENT: CodeAgentNode,
    NodeType.EXTERNAL_API: ExternalAPINode,
    NodeType.MCP: MCPNode,
    NodeType.DATASOURCE: DatasourceNode,
    NodeType.CHANNEL: ChannelNode,
    NodeType.HITL_NODE: HitlNode,
    NodeType.REFLECTION: ReflectionNode,
    NodeType.RESOURCE: ResourceNode,
}


class NodeConstructor:
    """Собирает ноду из конфига по уже известным зависимостям исполнения."""

    def __init__(
        self,
        *,
        workflow_runtime: DurableWorkflowRuntime,
        redis_client: RedisClient,
        emitter_factory: EmitterFactory,
        llm_context_memory_store: RAGLLMContextMemoryStore,
        namespace_service: NamespaceService,
        authz_service: AuthzService,
        text_transform_service: TextTransformService,
        billing_service: BillingService,
        handoff_orchestrator_service: HandoffOrchestratorService,
        a2a_client: A2AClient,
        code_agent_source_service: CodeAgentSourceService,
        guest_runtime_client: GuestRuntimeClient,
        variables_service: VariablesService,
        flow_access_service: FlowAccessService,
        datasource_service: DatasourceService,
        channel_registry: ChannelRegistryProtocol,
        mail_service: MailService,
        hitl_work_item_service: HitlWorkItemService,
        hitl_conversation_service: HitlConversationService,
    ) -> None:
        self.workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self.redis_client: RedisClient = redis_client
        self.emitter_factory: EmitterFactory = emitter_factory
        self.llm_context_memory_store: RAGLLMContextMemoryStore = llm_context_memory_store
        self.namespace_service: NamespaceService = namespace_service
        self.authz_service: AuthzService = authz_service
        self.text_transform_service: TextTransformService = text_transform_service
        self.billing_service: BillingService = billing_service
        self.handoff_orchestrator_service: HandoffOrchestratorService = handoff_orchestrator_service
        self.a2a_client: A2AClient = a2a_client
        self.code_agent_source_service: CodeAgentSourceService = code_agent_source_service
        self.guest_runtime_client: GuestRuntimeClient = guest_runtime_client
        self.variables_service: VariablesService = variables_service
        self.flow_access_service: FlowAccessService = flow_access_service
        self.datasource_service: DatasourceService = datasource_service
        self.channel_registry: ChannelRegistryProtocol = channel_registry
        self.mail_service: MailService = mail_service
        self.hitl_work_item_service: HitlWorkItemService = hitl_work_item_service
        self.hitl_conversation_service: HitlConversationService = hitl_conversation_service

    def build(
        self,
        node_cls: type[BaseNode],
        node_id: str,
        config: JsonObject,
        *,
        tool_registry: ToolRegistryProtocol,
        flow_factory: FlowFactoryProtocol,
    ) -> BaseNode:
        execution = execution_context_for(self.workflow_runtime)
        redis_client = self.redis_client
        emitter_factory = self.emitter_factory
        if issubclass(node_cls, LlmNode):
            return node_cls(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                flow_factory=flow_factory,
                llm_context_memory_store=self.llm_context_memory_store,
                namespace_service=self.namespace_service,
                authz_service=self.authz_service,
                tool_registry=tool_registry,
                workflow_runtime=self.workflow_runtime,
                text_transform_service=self.text_transform_service,
                billing_service=self.billing_service,
                emitter_factory=emitter_factory,
            )
        if node_cls is CodeNode:
            return CodeNode(node_id, config, execution=execution, redis_client=redis_client)
        if node_cls is FlowNode:
            return FlowNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                flow_factory=flow_factory,
                tool_registry=tool_registry,
                handoff_orchestrator_service=self.handoff_orchestrator_service,
            )
        if node_cls is RemoteFlowNode:
            return RemoteFlowNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                a2a_client=self.a2a_client,
                emitter_factory=emitter_factory,
            )
        if node_cls is CodeAgentNode:
            return CodeAgentNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                a2a_client=self.a2a_client,
                emitter_factory=emitter_factory,
                code_agent_source_service=self.code_agent_source_service,
                guest_runtime_client=self.guest_runtime_client,
            )
        if node_cls is ExternalAPINode:
            return ExternalAPINode(node_id, config, execution=execution, redis_client=redis_client)
        if node_cls is MCPNode:
            return MCPNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                variables_service=self.variables_service,
                flow_access_service=self.flow_access_service,
            )
        if node_cls is DatasourceNode:
            return DatasourceNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                datasource_service=self.datasource_service,
                datasource_executors=build_datasource_executors(
                    workflow_runtime=self.workflow_runtime,
                    flow_factory=flow_factory,
                    tool_registry=tool_registry,
                ),
            )
        if node_cls is ChannelNode:
            return ChannelNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                channel_registry=self.channel_registry,
                mail_service=self.mail_service,
            )
        if node_cls is HitlNode:
            return HitlNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                hitl_work_item_service=self.hitl_work_item_service,
                hitl_conversation_service=self.hitl_conversation_service,
            )
        if node_cls is ReflectionNode:
            return ReflectionNode(
                node_id,
                config,
                execution=execution,
                redis_client=redis_client,
                billing_service=self.billing_service,
            )
        if node_cls is ResourceNode:
            return ResourceNode(node_id, config, execution=execution, redis_client=redis_client)
        raise TypeError(f"Unknown node class: {node_cls!r}")

    def materialize(
        self,
        node_id: str,
        node_config: JsonObject,
        *,
        tool_registry: ToolRegistryProtocol,
        flow_factory: FlowFactoryProtocol,
    ) -> BaseNode:
        node_type_value = node_config.get("type")
        if not isinstance(node_type_value, str) or not node_type_value.strip():
            keys = sorted(node_config.keys())
            raise ValueError(
                f"Node '{node_id}': type is required as a non-empty string (fields: {keys})"
            )
        try:
            node_type = NodeType(node_type_value.strip())
        except ValueError:
            raise ValueError(f"Unknown node type: {node_type_value}")
        node_class = RUNTIME_NODE_CLASSES[node_type]
        return self.build(
            node_class,
            node_id,
            node_config,
            tool_registry=tool_registry,
            flow_factory=flow_factory,
        )


async def create_node(
    node_id: str,
    node_config: JsonObject,
    *,
    node_constructor: NodeConstructor,
    tool_registry: ToolRegistryProtocol,
    flow_factory: FlowFactoryProtocol,
) -> BaseNode:
    """
    Создаёт ноду через NodeRegistry.

    Zero-Guess: неизвестный тип = исключение.
    """
    node_config = dict(node_config)

    node_type_value = node_config.get("type")
    if not isinstance(node_type_value, str) or not node_type_value.strip():
        keys = sorted(node_config.keys())
        raise ValueError(
            f"Node '{node_id}': type is required as a non-empty string (fields: {keys})"
        )

    try:
        node_type = NodeType(node_type_value.strip())
    except ValueError:
        raise ValueError(f"Unknown node type: {node_type_value}")

    node_class = RUNTIME_NODE_CLASSES[node_type]
    return node_class.from_config(
        node_id,
        node_config,
        node_constructor=node_constructor,
        tool_registry=tool_registry,
        flow_factory=flow_factory,
    )
