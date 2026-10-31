"""
ReAct runner - реализация ReAct паттерна.

Zero-Guess: все методы работают с ExecutionState.
Stream-first: LLM ВСЕГДА вызывается как stream.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncGenerator, Sequence
from datetime import datetime, timezone
from typing import ClassVar, override

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import (
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from a2a.types.a2a_pb2 import ROLE_AGENT, ROLE_USER

from apps.flows.src.contracts import ToolRegistryProtocol
from apps.flows.src.durable_execution import (
    DurableWorkflowRuntime,
    ExecutionStateDelta,
    SideEffectPolicy,
    WorkflowEventType,
    apply_state_delta,
    build_state_delta,
    hash_state_json,
)
from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.models import NodeConfig, ReactLoopMode
from apps.flows.src.models.enums import NodeType, ReactToolRole
from apps.flows.src.runtime.a2a_messages import (
    build_assistant_message as new_assistant_message,
)
from apps.flows.src.runtime.a2a_messages import (
    build_system_message as new_system_message,
)
from apps.flows.src.runtime.a2a_messages import (
    build_tool_result_message as new_tool_result_message,
)
from apps.flows.src.runtime.a2a_messages import (
    build_user_message as new_user_message,
)
from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
    merge_tools_by_name,
)
from apps.flows.src.runtime.effective_llm_config import (
    EffectiveLLMConfig,
    resolve_effective_llm_config_for_node,
)
from apps.flows.src.runtime.exception_policy import (
    is_tool_arg_validation_error,
    should_absorb_exception,
)
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.llm_context_memory import (
    RuntimeMemoryWriteCommand,
    RuntimeMemoryWriteResult,
    apply_runtime_memory_cursor_advance,
    apply_runtime_memory_write_result,
    build_state_messages_memory_close_decision,
    write_runtime_memory_episode,
)
from apps.flows.src.runtime.tool_call_context import active_tool_call_context
from apps.flows.src.state import (
    ExecutionExceptionRecord,
    ExecutionState,
    InterruptPathItem,
    PromptHistoryItem,
)
from apps.flows.src.state.cancellation import (
    FlowCancelled,
    check_cancellation,
    get_cancellation_token,
)
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.state.mutation_policy import (
    FROZEN_STATE_FIELDS,
    USER_TOOL_PARALLEL_STATE_MERGE_FIELDS,
)
from apps.flows.src.streaming import BaseEmitter
from apps.flows.src.streaming.emitter import EmitterFactory
from apps.flows.src.tools.base import BaseTool, OpenAIToolSchema, ToolArguments, sanitize_tool_name
from core.a2a import (
    get_part_text,
    mapping_from_struct,
    message_from_json_dict,
    message_to_json_dict,
    part_has_text,
)
from core.ai.providers import AICapability
from core.ai.runtime import create_llm_client_from_call_config
from core.clients.llm import (
    LLMClient,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
    LLMToolCall,
    MockLLM,
    StreamEvent,
)
from core.clients.llm.mock_control import (
    resolve_llm_node_mock,
    resolve_tool_mock_result,
)
from core.clients.nano_banana import NanoBananaClient
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.errors import FlowExecutionError, ToolExecutionError
from core.files.file_ref import stored_file_ref
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.llm_context import (
    LLMContextBlock,
    LLMContextProfile,
    LLMContextSourceRegistry,
)
from core.llm_context.memory import LLMContextMemoryStore
from core.llm_context.memory_compaction import LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_FLOW_MEMORY_SUMMARIZE,
    EVENT_FLOW_REACT_COMPLETED,
    LOG_FLOW_ID,
    LOG_FLOW_MEMORY_COMPACTION,
    LOG_FLOW_MEMORY_SUMMARIZE_MS,
    LOG_FLOW_REACT_INTERRUPTED,
    LOG_FLOW_REACT_ITERATIONS,
    LOG_FLOW_REACT_MAX_ITERATIONS,
    LOG_TASK_ID,
)
from core.text_transforms.service import TextTransformService
from core.tracing import TraceContext, get_tracer
from core.tracing.attributes import (
    ATTR_MEMORY_COMPACTION,
    ATTR_MEMORY_CURSOR_END,
    ATTR_MEMORY_CURSOR_KEY,
    ATTR_MEMORY_CURSOR_START,
    ATTR_MEMORY_SCOPE,
    ATTR_NODE_ID,
    ATTR_WORKFLOW_EXECUTION_BRANCH_ID,
    ATTR_WORKFLOW_NODE_SCHEDULE_SEQUENCE,
    ATTR_WORKFLOW_SESSION_ID,
)
from core.tracing.context import get_current_trace_context
from core.tracing.operation_span import traced_operation
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_object,
)
from core.variables import VariableResolver

from .base_runner import BaseLlmNodeRunner, LlmNodeRunnerHost

logger = get_logger(__name__)

def _runtime_message(value: Message | JsonObject) -> Message:
    if isinstance(value, Message):
        return value
    return message_from_json_dict(value)


def _get_trace_ctx_from_state() -> TraceContext | None:
    """Получает TraceContext из ContextVar worker'а."""
    trace_data = get_current_trace_context()
    if trace_data:
        return TraceContext.from_dict(trace_data)
    return None


def _get_message_metadata(msg: Message | JsonObject) -> JsonObject:
    """Получает metadata из Message."""
    message = _runtime_message(msg)
    if not message.HasField("metadata"):
        return {}
    return mapping_from_struct(message.metadata)


def _message_plain_text(msg: Message) -> str:
    return get_message_text(msg)


def _user_message_already_in_task(
    messages: Sequence[Message | JsonObject],
    text: str,
    task_id: str | None,
) -> bool:
    """Idempotent guard: тот же user text уже записан для этого A2A task_id."""
    if task_id is None or task_id.strip() == "" or text == "":
        return False
    for raw in reversed(messages):
        message = _runtime_message(raw)
        if message.role != ROLE_USER:
            continue
        if message.task_id != task_id:
            continue
        if _message_plain_text(message) == text:
            return True
    return False


def _assistant_message_already_in_task(
    messages: Sequence[Message | JsonObject],
    text: str,
    task_id: str | None,
) -> bool:
    """Idempotent guard: тот же agent text уже записан для этого A2A task_id."""
    if task_id is None or task_id.strip() == "" or text == "":
        return False
    for raw in reversed(messages):
        message = _runtime_message(raw)
        if message.role != ROLE_AGENT:
            continue
        if message.task_id != task_id:
            continue
        if _message_plain_text(message) == text:
            return True
        # Смотрим только последнее agent-сообщение этого task.
        return False
    return False


def _get_tool_calls_metadata(metadata: JsonObject, field_name: str) -> list[LLMToolCall] | None:
    raw_tool_calls = metadata.get("tool_calls")
    if raw_tool_calls is None:
        return None
    if not isinstance(raw_tool_calls, list):
        raise ValueError(f"{field_name}.tool_calls must be a list")
    tool_calls: list[LLMToolCall] = []
    for index, item in enumerate(raw_tool_calls):
        if not isinstance(item, dict):
            raise ValueError(f"{field_name}.tool_calls[{index}] must be an object")
        tool_calls.append(LLMToolCall.model_validate(item))
    return tool_calls


def _copy_state_projection(target: ExecutionState, source: ExecutionState) -> None:
    data = source.model_dump(mode="python", exclude_none=False)
    for field_name in ExecutionState.model_fields:
        if field_name in data:
            if field_name == "messages":
                target.messages = [_runtime_message(msg) for msg in source.messages]
                continue
            target[field_name] = data[field_name]
    extras = require_json_object(source.__pydantic_extra__ or {}, "state.extra")
    for key, value in extras.items():
        if key not in FROZEN_STATE_FIELDS:
            target[key] = value


def _format_tool_result_content(result: JsonValue) -> str:
    """Строка tool_result для LLM history и SSE: JSON для объектов, не Python repr."""
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


class LlmNodeRunner(BaseLlmNodeRunner):
    """
    Runner для LLM-нод (ReAct цикл).
    Stream-first: ТОЛЬКО STREAM!
    """

    MAX_ITERATIONS: ClassVar[int] = 25
    MAX_STREAM_IDLE_RETRIES: ClassVar[int] = 4  # При idle timeout 10с — макс 50с ожидания (5 попыток × 10с)
    tools: list[BaseTool]

    def __init__(
        self,
        node_config: NodeConfig,
        tools: list[BaseTool],
        llm: LLMClient | MockLLM | None,
        prompt: str,
        llm_node: LlmNodeRunnerHost | None = None,
        *,
        workflow_runtime: DurableWorkflowRuntime,
        memory_store: LLMContextMemoryStore,
        text_transform_service: TextTransformService,
        emitter_factory: EmitterFactory,
        redis_client: RedisClient,
        tool_registry: ToolRegistryProtocol,
        llm_context_policy: LLMContextProfile | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
        agent_skill_host: AgentSkillRuntimeHost | None = None,
    ):
        super().__init__(
            node_config=node_config,
            tools=tools,
            llm=llm,
            prompt=prompt,
            llm_node=llm_node,
        )
        self.workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self.memory_store: LLMContextMemoryStore = memory_store
        self.text_transform_service: TextTransformService = text_transform_service
        self.emitter_factory: EmitterFactory = emitter_factory
        self.redis_client: RedisClient = redis_client
        self.tool_registry: ToolRegistryProtocol = tool_registry
        self.llm_context_policy: LLMContextProfile | None = llm_context_policy
        self.llm_context_source_registry: LLMContextSourceRegistry | None = llm_context_source_registry
        self.agent_skill_host: AgentSkillRuntimeHost | None = agent_skill_host
        if self.agent_skill_host is not None:
            self.agent_skill_host.ensure_index_block()
        self._vision_bytes: dict[str, bytes] = {}

    async def _checkpoint_state(
        self,
        state: ExecutionState,
        *,
        event_type: WorkflowEventType = WorkflowEventType.state_projection_committed,
        payload: JsonObject | None = None,
    ) -> None:
        _ = state
        _ = event_type
        _ = payload
        return

    async def _close_context_memory_window(self, state: ExecutionState) -> None:
        if not self._context_memory_writes_enabled():
            return

        decision = build_state_messages_memory_close_decision(
            state=state,
            node_id=self._source_node_id(),
            policy=self.llm_context_policy,
            messages=self._messages_for_llm_context(state),
        )
        if decision is None:
            return
        if decision.episode is None:
            apply_runtime_memory_cursor_advance(state, decision)
            return

        execution_branch_id = state.durable_execution_branch_id
        if execution_branch_id is None:
            raise RuntimeError("Memory write requires durable execution_branch_id")
        node_schedule_sequence = state.durable_node_schedule_sequence
        if node_schedule_sequence is None:
            raise RuntimeError("Memory write requires NodeScheduled.sequence")

        command = RuntimeMemoryWriteCommand(
            session_id=state.session_id,
            execution_branch_id=execution_branch_id,
            node_schedule_sequence=node_schedule_sequence,
            node_id=self._source_node_id(),
            cursor_key=decision.cursor_key,
            cursor=decision.cursor,
            next_cursor=decision.next_cursor,
            episode=decision.episode,
            compaction=decision.compaction,
        )
        _ = await self._run_context_memory_write_activity(state, command)

    async def _run_context_memory_write_activity(
        self,
        state: ExecutionState,
        command: RuntimeMemoryWriteCommand,
    ) -> RuntimeMemoryWriteResult:
        input_payload = require_json_object(
            command.model_dump(mode="json"),
            "memory_write.activity_input",
        )
        activity_id = (
            f"{command.session_id}:{command.execution_branch_id}:node:{command.node_id}:"
            + f"memory_write:schedule:{command.node_schedule_sequence}:"
            + f"input:{hash_state_json(input_payload)}"
        )
        runtime = self.workflow_runtime
        scheduled_result = await runtime.record_activity_scheduled(
            session_id=state.session_id,
            activity_id=activity_id,
            activity_type="memory_write",
            input_payload=input_payload,
            node_id=command.node_id,
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.idempotent,
        )
        if scheduled_result is not None:
            result = self._apply_replayed_memory_activity_result(
                state,
                scheduled_result,
            )
            logger.info(
                "llm_context.memory_write_replayed",
                memory_id=result.memory_id,
                cursor_key=result.cursor_key,
                node_id=command.node_id,
                session_id=command.session_id,
                execution_branch_id=command.execution_branch_id,
            )
            return result

        started = await runtime.record_activity_started(activity_id=activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark memory write activity as started: {activity_id!r}")

        trace_ctx = _get_trace_ctx_from_state()
        tracer = get_tracer()
        before_state = ExecutionState.model_validate(
            state.model_dump(mode="python", exclude_none=False)
        )
        try:
            async with tracer.platform_operation_span(
                "flows.memory.write",
                event_type="llm_context.memory_write",
                resource_type="llm_context_memory",
                resource_id=command.episode.memory_id,
                trace_ctx=trace_ctx,
                extra_attributes={
                    ATTR_WORKFLOW_SESSION_ID: command.session_id,
                    ATTR_WORKFLOW_EXECUTION_BRANCH_ID: command.execution_branch_id,
                    ATTR_WORKFLOW_NODE_SCHEDULE_SEQUENCE: command.node_schedule_sequence,
                    ATTR_NODE_ID: command.node_id,
                    ATTR_MEMORY_CURSOR_KEY: command.cursor_key,
                    ATTR_MEMORY_CURSOR_START: command.cursor,
                    ATTR_MEMORY_CURSOR_END: command.next_cursor,
                    ATTR_MEMORY_SCOPE: command.episode.scope,
                    ATTR_MEMORY_COMPACTION: command.compaction,
                },
            ):
                result = await write_runtime_memory_episode(
                    store=self.memory_store,
                    command=command,
                    summarize_episode=self._summarize_context_memory_episode,
                )
                apply_runtime_memory_write_result(state, result)
        except Exception as exc:
            completed_failed = await runtime.record_activity_completed(
                activity_id=activity_id,
                error=str(exc),
            )
            if not completed_failed:
                raise RuntimeError(f"Failed to mark memory write activity as failed: {activity_id!r}") from exc
            raise

        state_delta = build_state_delta(before_state, state)
        result_json = require_json_object(
            {
                "result": result.model_dump(mode="json"),
                "state_delta": state_delta.model_dump(mode="json", exclude_none=False),
            },
            "memory_write.activity_result",
        )
        completed_ok = await runtime.record_activity_completed(
            activity_id=activity_id,
            result_json=result_json,
        )
        if not completed_ok:
            raise RuntimeError(f"Failed to mark memory write activity as completed: {activity_id!r}")
        logger.info(
            "llm_context.memory_write_completed",
            memory_id=result.memory_id,
            cursor_key=result.cursor_key,
            node_id=command.node_id,
            session_id=command.session_id,
            execution_branch_id=command.execution_branch_id,
        )
        return result

    @staticmethod
    def _apply_replayed_memory_activity_result(
        state: ExecutionState,
        completed: JsonObject,
    ) -> RuntimeMemoryWriteResult:
        if "state_delta" not in completed:
            raise ValueError("memory_write activity result missing state_delta")
        delta_raw = completed["state_delta"]
        if not isinstance(delta_raw, dict):
            raise ValueError("memory_write activity state_delta must be an object")
        replayed_state = apply_state_delta(
            state,
            ExecutionStateDelta.model_validate(delta_raw),
        )
        _copy_state_projection(state, replayed_state)

        if "result" not in completed:
            raise ValueError("memory_write activity result missing result")
        result_raw = completed["result"]
        if not isinstance(result_raw, dict):
            raise ValueError("memory_write activity result must be an object")
        result = RuntimeMemoryWriteResult.model_validate(result_raw)
        apply_runtime_memory_write_result(state, result)
        return result

    def _context_memory_writes_enabled(self) -> bool:
        policy = self.llm_context_policy
        return (
            policy is not None
            and policy.mode != "off"
            and policy.memory != "off"
            and policy.compaction != "off"
        )

    def _context_memory_uses_full_state_messages(self) -> bool:
        if self.llm_node is None:
            return True
        return self.llm_node.messages_filter == "all"

    async def _summarize_context_memory_episode(self, text: str) -> str:
        effective = resolve_effective_llm_config_for_node(self.node_config)
        llm_config = effective.config
        summarize_start = time.perf_counter()
        async with traced_operation(
            "flows.memory.summarize",
            event_type="llm_context.memory_summarize",
            operation_category="llm",
            resource_type="llm_context_memory",
            trace_ctx=_get_trace_ctx_from_state(),
        ):
            summary = await self.text_transform_service.summarize(
                text,
                max_output_tokens=700,
                instruction=LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION,
                provider=llm_config.provider,
                model=llm_config.model,
            )
        summarize_ms = round((time.perf_counter() - summarize_start) * 1000.0, 3)
        logger.info(
            EVENT_FLOW_MEMORY_SUMMARIZE,
            **{
                LOG_FLOW_MEMORY_SUMMARIZE_MS: summarize_ms,
                LOG_FLOW_MEMORY_COMPACTION: "llm_summary",
                "summary_text_length": len(summary),
                "source_text_length": len(text),
            },
        )
        return summary

    def _resolve_tool_by_call_name(self, call_name: str) -> BaseTool | None:
        """Резолвит tool по имени вызова, включая API-совместимую санитизацию."""
        exact_tool = next((t for t in self.tools if t.name == call_name), None)
        if exact_tool:
            return exact_tool

        sanitized_name = sanitize_tool_name(call_name)
        sanitized_tool = next((t for t in self.tools if t.name == sanitized_name), None)
        if sanitized_tool:
            return sanitized_tool

        return None

    def _source_node_id(self) -> str:
        if not self.node_config:
            raise ValueError("LlmNodeRunner.node_config required for message tagging")
        return self.node_config.node_id

    def _exception_policy_from_node_config(self) -> tuple[bool, list[str]]:
        if not self.node_config:
            return False, []
        names = [x.value for x in self.node_config.exception_allow_types]
        return (self.node_config.exception_as_response, names)

    def _record_tool_exception(
        self,
        state: ExecutionState,
        tool_name: str,
        tool_call_id: str,
        exc: BaseException,
    ) -> None:
        state.execution_exceptions.append(
            ExecutionExceptionRecord(
                node_id=self._source_node_id(),
                source="tool",
                exception_type=type(exc).__name__,
                message=str(exc),
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
        )

    @staticmethod
    def _format_tool_error_content(tool_name: str, exc: BaseException) -> str:
        return (
            f"Ошибка инструмента '{tool_name}': {type(exc).__name__}: {exc}"
        )

    def _messages_for_llm_context(self, state: ExecutionState) -> list[Message]:
        if self.llm_node is not None:
            return [_runtime_message(msg) for msg in self.llm_node.get_filtered_messages(state)]
        return [_runtime_message(msg) for msg in state.messages]

    @override
    async def run(
        self,
        input_data: JsonObject,
        state: ExecutionState,
        emitter: BaseEmitter | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Выполняет ReAct цикл.

        Аргументы:
            input_data: Входные данные
            state: ExecutionState агента
            emitter: Emitter для публикации событий (BaseEmitter или его наследники)
        """
        task_id = state.task_id
        context_id = state.context_id

        if emitter is None:
            emitter = await self.emitter_factory.create(state)

        raw_user_content = input_data.get("content", "")
        if not isinstance(raw_user_content, str):
            raise ValueError("llm input_data.content must be a string")
        user_content = raw_user_content
        llm_node_label = self.node_config.name if self.node_config else "unknown"
        sid = self._source_node_id()

        interrupt_path = InterruptManager.get_interrupt_path(state)

        if interrupt_path:
            if user_content:
                await self._handle_resume(
                    state, user_content, interrupt_path, context_id, task_id
                )
                await self._checkpoint_state(state)
            else:
                InterruptManager.clear_interrupt_path(state)
        elif user_content:
            if not _user_message_already_in_task(state.messages, user_content, task_id):
                state.messages.append(
                    new_user_message(
                        user_content, sid, context_id=context_id, task_id=task_id
                    )
                )
                await self._checkpoint_state(state)

        effective_llm = resolve_effective_llm_config_for_node(self.node_config)
        if effective_llm.capability == AICapability.IMAGE_GEN:
            await self._run_image_gen(
                state, user_content, context_id=context_id, task_id=task_id
            )
            return

        async for event in self._react_loop(
            state, llm_node_label, context_id, task_id, emitter
        ):
            yield event

    async def _run_image_gen(
        self,
        state: ExecutionState,
        user_content: str,
        *,
        context_id: str,
        task_id: str,
    ) -> None:
        """Исполнение ``image_gen`` ноды: промпт + image-референсы ``state.files`` → file_ids.

        Image-файлы из ``state.files`` идут референсами генерации; их наличие
        включает режим редактирования (enhance), отсутствие — генерацию с нуля.
        Результат — ``{"file_ids": [...]}`` в ``state.response``, FileRef'ы
        дописываются в ``state.files``.
        """
        sid = self._source_node_id()
        system_prompt = await self._render_prompt(state)
        prompt = system_prompt
        if user_content.strip():
            prompt = (
                f"{system_prompt}\n\n{user_content.strip()}"
                if system_prompt.strip()
                else user_content.strip()
            )
        references = [
            ref
            for ref in state.files
            if ref.file_id is not None
            and bool(ref.file_id.strip())
            and ref.content_type.startswith("image/")
        ]
        file_ids = await NanoBananaClient().generate_images(
            prompt=prompt,
            reference_file_ids=[ref.file_id for ref in references if ref.file_id is not None]
            or None,
            num_images=1,
            is_editing=bool(references),
        )
        if not file_ids:
            raise FlowExecutionError(
                message=f"LLM node '{sid}': image_gen returned no files",
                payload={"node_id": sid},
            )
        for file_id in file_ids:
            record = await FileRecord.get(file_id)
            if record is None:
                raise ValueError(f"image_gen produced unknown file: {file_id}")
            upsert_state_file(state, stored_file_ref(record))
        response = json.dumps({"file_ids": file_ids}, ensure_ascii=False)
        state.messages.append(
            new_assistant_message(
                response, sid, None, context_id=context_id, task_id=task_id
            )
        )
        state.response = response
        await self._checkpoint_state(state)

    def _messages_to_dict(self, messages: Sequence[Message | JsonObject]) -> list[JsonObject]:
        """Конвертирует Message объекты в dict для трейсинга."""
        result: list[JsonObject] = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(require_json_object(msg, "llm.message"))
                continue
            result.append(require_json_object(message_to_json_dict(msg), "llm.message"))
        return result

    async def _active_execution_branch_id(self, state: ExecutionState) -> str:
        position = await self.workflow_runtime.get_active_execution_position(
            state.session_id
        )
        if position is None:
            raise RuntimeError(
                f"Workflow instance is required before scheduling LLM activity: {state.session_id!r}"
            )
        return position.execution_branch_id

    def _get_react_config(self) -> tuple[ReactLoopMode, str, int, bool, str | None]:
        """Возвращает конфигурацию ReAct цикла."""
        if self.node_config and self.node_config.react:
            react = self.node_config.react
            return react.loop_mode, react.exit_tool, react.max_iterations, react.strict, react.reminder_message
        return ReactLoopMode.AUTO, "finish", self.MAX_ITERATIONS, True, None

    def _find_exit_tool_call(
        self, tool_calls: list[LLMToolCall], exit_tool: str
    ) -> LLMToolCall | None:
        """Ищет exit tool среди tool_calls."""
        for tc in tool_calls:
            if tc.name == exit_tool:
                return tc
        return None

    def _find_tool_call_in_messages(
        self, messages: Sequence[Message | JsonObject], tool_name: str
    ) -> LLMToolCall | None:
        """Ищет tool_call по имени в последнем assistant сообщении."""
        for msg in reversed(messages):
            metadata = _get_message_metadata(msg)
            tool_calls = _get_tool_calls_metadata(metadata, "message.metadata")
            if tool_calls:
                for tc in tool_calls:
                    if tc.name == tool_name:
                        return tc
                break
        return None

    def _ensure_assistant_tool_calls(
        self,
        state: ExecutionState,
        tool_call_id: str,
        tool_call: LLMToolCall,
        context_id: str,
        task_id: str | None = None,
    ) -> None:
        """Гарантирует наличие assistant.tool_calls перед tool_result."""
        sid = self._source_node_id()
        for msg in reversed(state.messages):
            metadata = _get_message_metadata(msg)
            tool_calls = _get_tool_calls_metadata(metadata, "message.metadata")
            if tool_calls:
                for tc in tool_calls:
                    if tc.id == tool_call_id:
                        return
                break
        state.messages.append(
            new_assistant_message(
                "", sid, [tool_call], context_id=context_id, task_id=task_id
            )
        )

    async def _handle_resume(
        self,
        state: ExecutionState,
        user_answer: str,
        interrupt_path: list[InterruptPathItem],
        context_id: str,
        task_id: str | None = None,
    ) -> None:
        """Обрабатывает resume после interrupt."""
        if not interrupt_path:
            return

        next_call = interrupt_path[0]
        call_type = next_call.node_type
        call_id = next_call.node_id
        tool_call = next_call.tool_call

        if tool_call is None:
            tool_call = self._find_tool_call_in_messages(state.messages, call_id)
        if tool_call is None:
            tool_call = LLMToolCall(id=call_id, name=call_id, arguments={})

        tool_call_id = tool_call.id
        sid = self._source_node_id()

        logger.info(
            "llm.resume",
            call_type=call_type,
            call_id=call_id,
            tool_call_id=tool_call_id,
            path_len=len(interrupt_path),
            answer_preview=user_answer[:50],
        )

        if call_type == NodeType.LLM_NODE.value:
            # NodeAsToolWrapper сам обрабатывает resume через interrupt_path
            # Передаем ответ пользователя в state.content
            state.content = user_answer

            try:
                tool_results = await self._execute_tools_parallel(
                    [LLMToolCall(name=call_id, id=tool_call_id, arguments={"query": user_answer})],
                    state,
                )
                for tr in tool_results:
                    state.messages.append(
                        new_tool_result_message(
                            tr["tool_call_id"],
                            tr["content"],
                            sid,
                            context_id=context_id,
                            task_id=task_id,
                        )
                    )
                InterruptManager.clear_interrupt_path(state)
            except FlowInterrupt as e:
                InterruptManager.apply_interrupt(
                    state, e.body, tool_call, e.correlation_id
                )
                await self._checkpoint_state(state)
                raise
        else:
            self._ensure_assistant_tool_calls(
                state, tool_call_id, tool_call, context_id, task_id
            )
            state.messages.append(
                new_tool_result_message(
                    tool_call_id,
                    user_answer,
                    sid,
                    context_id=context_id,
                    task_id=task_id,
                )
            )

        InterruptManager.clear_interrupt_path(state)
        await self._checkpoint_state(state)

    def _append_interrupted_stream_assistant(
        self,
        state: ExecutionState,
        content: str,
        *,
        sid: str,
        context_id: str,
        task_id: str,
    ) -> None:
        text = content.strip()
        if text == "":
            return
        state.messages.append(
            new_assistant_message(
                text,
                sid,
                None,
                context_id=context_id,
                task_id=task_id,
                interrupted=True,
            )
        )

    async def _react_loop(
        self,
        state: ExecutionState,
        llm_node_label: str,
        context_id: str,
        task_id: str,
        emitter: BaseEmitter,
    ) -> AsyncGenerator[StreamEvent, None]:
        """ReAct цикл со стримингом событий."""
        sid = self._source_node_id()
        system_prompt = await self._render_prompt(state)
        trace_ctx = _get_trace_ctx_from_state()
        tracer = get_tracer()
        effective_llm = resolve_effective_llm_config_for_node(self.node_config)
        llm_config = effective_llm.config
        model = llm_config.model or "unknown"

        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Context with active_company is required for the LLM node")
        if not str(actx.user.user_id).strip():
            raise ValueError("Context with user is required for the LLM node (billing and notifications)")
        mock_llm_client = await resolve_llm_node_mock(
            self.redis_client, state.session_id, self._source_node_id()
        )
        # Определяем режим: structured_output или tools
        structured_output = self.node_config.structured_output if self.node_config else False
        output_schema = self.node_config.output_schema if self.node_config else None

        if structured_output and output_schema:
            tools_schema = None
            response_format: JsonObject | None = require_json_object(
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "strict": True,
                        "schema": output_schema,
                    },
                },
                "llm.response_format",
            )
            schema_properties = output_schema.get("properties")
            schema_keys = list(schema_properties.keys()) if isinstance(schema_properties, dict) else []
            logger.info(
                "llm.structured_output",
                node=llm_node_label,
                schema_keys=schema_keys,
            )
        else:
            tools_schema = self._build_tools_schema()
            response_format = None

        loop_mode, exit_tool, max_iterations, strict, reminder_message = self._get_react_config()
        reason_tool = self._find_tool_by_react_role(ReactToolRole.REASON)
        reason_tool_name = reason_tool.name if reason_tool else None
        exit_tool_obj = self._find_tool_by_react_role(ReactToolRole.EXIT)
        exit_tool_name = (exit_tool_obj.name if exit_tool_obj else None) or exit_tool

        system_msg = new_system_message(
            system_prompt, context_id=context_id, task_id=task_id
        )

        iteration = 0
        final_response = ""

        async with tracer.llm_node_span(llm_node_label, model=model, trace_ctx=trace_ctx) as llm_node_span:
            try:
                while iteration < max_iterations:
                    iteration += 1

                    await check_cancellation(state)

                    if tools_schema is not None:
                        tools_schema = self._build_tools_schema()

                    logger.debug("flows.llm.react_iteration", llm_node=llm_node_label, iteration=iteration)

                    messages = self._messages_for_llm_context(state)

                    async with tracer.react_iteration_span(
                        iteration, llm_node_label, trace_ctx=trace_ctx
                    ):
                        llm_messages = [system_msg] + messages
                        llm_call_messages = llm_messages
                        if effective_llm.capability == AICapability.LLM_VISION:
                            llm_call_messages = await self._with_vision_file_parts(
                                state, llm_messages
                            )
                        content = ""
                        tool_calls: list[LLMToolCall] | None = None
                        had_reasoning_event = False
                        llm_start = time.time()
                        resolved_llm_model: str | None = None
                        resolved_llm_provider: str | None = None
                        resolved_llm_source: str | None = None

                        llm, max_tok = self._resolve_llm_client(
                            state,
                            effective_llm=effective_llm,
                            mock_llm_client=mock_llm_client,
                        )
                        llm_provider = llm.llm_provider

                        async with traced_operation(
                            "flows.llm_node.call",
                            event_type="llm.call",
                            operation_category="llm",
                            resource_type="llm",
                            trace_ctx=trace_ctx,
                            extra_attributes={
                                "llm.model": model,
                                "llm.provider": llm_provider,
                                "llm.message_count": len(llm_messages),
                                "llm.tool_count": len(tools_schema) if tools_schema else 0,
                            },
                        ) as llm_span:
                            llm_messages_for_trace = self._messages_to_dict(llm_messages)
                            tracer.record_llm_request(llm_span, llm_messages_for_trace, tools_schema, response_format)

                            try:
                                async for event in self._call_llm(
                                    llm,
                                    max_tok,
                                    llm_call_messages,
                                    tools_schema,
                                    context_id,
                                    task_id,
                                    response_format,
                                    state,
                                    iteration=iteration,
                                ):
                                    should_yield = True

                                    if isinstance(event, TaskArtifactUpdateEvent):
                                        artifact_name = event.artifact.name or "response"
                                        if artifact_name == "reasoning":
                                            had_reasoning_event = True
                                        if artifact_name != "reasoning":
                                            for part in event.artifact.parts:
                                                if part_has_text(part):
                                                    content += get_part_text(part)
                                            if loop_mode == ReactLoopMode.EXPLICIT:
                                                should_yield = False

                                    if should_yield:
                                        await emitter.emit(event)
                                        yield event

                                    if isinstance(event, TaskStatusUpdateEvent):
                                        if (
                                            event.status.message
                                            and event.status.message.HasField("metadata")
                                        ):
                                            md = _get_message_metadata(event.status.message)
                                            tc = _get_tool_calls_metadata(md, "llm.event.metadata")
                                            if tc:
                                                tool_calls = tc
                                            md_model = md.get("model")
                                            if isinstance(md_model, str) and md_model.strip():
                                                resolved_llm_model = md_model.strip()
                                            md_provider = md.get("provider")
                                            if isinstance(md_provider, str) and md_provider.strip():
                                                resolved_llm_provider = md_provider.strip()
                                            md_source = md.get("source")
                                            if isinstance(md_source, str) and md_source.strip():
                                                resolved_llm_source = md_source.strip()
                            except FlowCancelled:
                                self._append_interrupted_stream_assistant(
                                    state,
                                    content,
                                    sid=sid,
                                    context_id=context_id,
                                    task_id=task_id,
                                )
                                raise

                            if resolved_llm_model:
                                logger.info(
                                    "llm.call_resolved",
                                    requested_model=model,
                                    provider=resolved_llm_provider or llm_provider,
                                    model=resolved_llm_model,
                                    source=resolved_llm_source,
                                    duration_ms=round((time.time() - llm_start) * 1000),
                                )

                        if tool_calls:
                            tool_names = [tc.name for tc in tool_calls]
                            logger.info("flows.llm.tools_requested", llm_node=llm_node_label, tool_names=tool_names)

                            exit_call = self._find_exit_tool_call(tool_calls, exit_tool_name)

                            if exit_call and loop_mode == ReactLoopMode.EXPLICIT:
                                exit_args = exit_call.arguments
                                exit_tool = next(t for t in self.tools if t.name == exit_tool_name)
                                result = await exit_tool.run(exit_args, state)
                                final_response = str(result) if not isinstance(result, str) else result

                                logger.info(
                                    "llm.exit_tool",
                                    node=llm_node_label,
                                    exit_tool_name=exit_tool_name,
                                )

                                state.messages.append(
                                    new_assistant_message(
                                        content,
                                        sid,
                                        tool_calls,
                                        context_id=context_id,
                                        task_id=task_id,
                                    )
                                )

                                exit_call_id = exit_call.id
                                await emitter.emit_tool_call(exit_tool_name, exit_args, exit_call_id)

                                state.messages.append(
                                    new_tool_result_message(
                                        exit_call_id,
                                        final_response,
                                        sid,
                                        context_id=context_id,
                                        task_id=task_id,
                                    )
                                )
                                await emitter.emit_tool_result(exit_tool_name, final_response, exit_call_id)
                                state.response = final_response
                                InterruptManager.clear_interrupt_path(state)
                                await self._checkpoint_state(state)
                                break

                            state.messages.append(
                                new_assistant_message(
                                    content,
                                    sid,
                                    tool_calls,
                                    context_id=context_id,
                                    task_id=task_id,
                                )
                            )

                            for tc in tool_calls:
                                tool_call_id = tc.id
                                tool_name = tc.name
                                tool_args = tc.arguments

                                tool_obj = self._resolve_tool_by_call_name(tool_name)
                                react_role = (
                                    tool_obj.react_role.value
                                    if tool_obj
                                    else ReactToolRole.STANDARD.value
                                )

                                await emitter.emit_tool_call(
                                    tool_name, tool_args, tool_call_id, react_role
                                )

                            try:
                                tool_results = await self._execute_tools_parallel(
                                    tool_calls, state, trace_ctx, emitter
                                )

                                for tr in tool_results:
                                    state.messages.append(
                                        new_tool_result_message(
                                            tr["tool_call_id"],
                                            tr["content"],
                                            sid,
                                            context_id=context_id,
                                            task_id=task_id,
                                        )
                                    )
                                    tool_call_id = tr["tool_call_id"]
                                    tool_name = next(
                                        (
                                            tc.name
                                            for tc in tool_calls
                                            if tc.id == tool_call_id
                                        ),
                                        "unknown",
                                    )
                                    await emitter.emit_tool_result(
                                        tool_name, tr["content"], tool_call_id
                                    )
                                pending_reasoning = state.pending_reasoning
                                if pending_reasoning:
                                    await emitter.emit_reasoning(
                                        json.dumps(pending_reasoning, ensure_ascii=False)
                                    )
                                    state.pending_reasoning = None

                                await self._checkpoint_state(state)

                                if state.terminal_task_state == "handback":
                                    final_response = state.response or ""
                                    InterruptManager.clear_interrupt_path(state)
                                    break

                            except FlowInterrupt as e:
                                interrupted_tc = e.tool_call or tool_calls[0]
                                logger.info(
                                    "llm.interrupt",
                                    node=llm_node_label,
                                    tool=interrupted_tc.name,
                                )

                                async with tracer.interrupt_span(
                                    e.question, interrupted_tc.name, trace_ctx=trace_ctx
                                ):
                                    # Добавляем элемент в путь только если это первичный interrupt
                                    # (не от вложенного субагента)
                                    if not state.interrupt_path:
                                        InterruptManager.push_interrupt_path(
                                            state,
                                            InterruptPathItem(
                                                node_type="tool",
                                                node_id=interrupted_tc.name,
                                                tool_call=interrupted_tc,
                                            ),
                                        )

                                    InterruptManager.apply_interrupt(
                                        state,
                                        e.body,
                                        interrupted_tc,
                                        e.correlation_id,
                                    )
                                await self._checkpoint_state(state)
                                raise
                        else:
                            if had_reasoning_event and not content:
                                await self._checkpoint_state(state)
                                continue

                            # Структурированный вывод — всегда завершаем после первого ответа
                            if structured_output and output_schema:
                                try:
                                    parsed_output = parse_json_value(content, "llm.structured_output")
                                    state.set_structured_output_result(parsed_output)
                                    final_response = content
                                    parsed_output_keys: list[str] = (
                                        list(parsed_output.keys())
                                        if isinstance(parsed_output, dict)
                                        else []
                                    )
                                    logger.info(
                                        "flows.llm.structured_output_received",
                                        llm_node=llm_node_label,
                                        output_keys=parsed_output_keys or type(parsed_output).__name__,
                                    )
                                except ValueError as e:
                                    logger.error("flows.llm.structured_output_parse_failed", llm_node=llm_node_label, error=str(e))
                                    final_response = content

                                state.messages.append(
                                    new_assistant_message(
                                        final_response, sid, None, context_id=context_id, task_id=task_id
                                    )
                                )
                                InterruptManager.clear_interrupt_path(state)
                                await self._checkpoint_state(state)
                                break

                            if loop_mode == ReactLoopMode.AUTO:
                                final_response = content
                                logger.info(
                                    "llm.final_response",
                                    node=llm_node_label,
                                    preview=final_response[:100],
                                )
                                if not _assistant_message_already_in_task(
                                    state.messages, final_response, task_id
                                ):
                                    state.messages.append(
                                        new_assistant_message(
                                            final_response,
                                            sid,
                                            None,
                                            context_id=context_id,
                                            task_id=task_id,
                                        )
                                    )
                                InterruptManager.clear_interrupt_path(state)
                                await self._checkpoint_state(state)
                                break
                            else:
                                if not strict:
                                    final_response = content
                                    logger.info(
                                        "llm.explicit_text_accepted",
                                        node=llm_node_label,
                                    )
                                    if not _assistant_message_already_in_task(
                                        state.messages, final_response, task_id
                                    ):
                                        state.messages.append(
                                            new_assistant_message(
                                                final_response,
                                                sid,
                                                None,
                                                context_id=context_id,
                                                task_id=task_id,
                                            )
                                        )
                                    InterruptManager.clear_interrupt_path(state)
                                    await self._checkpoint_state(state)
                                    break

                                logger.warning(
                                    "llm.explicit_missing_exit_tool",
                                    node=llm_node_label,
                                    exit_tool_name=exit_tool_name,
                                )
                                state.messages.append(
                                    new_assistant_message(content, sid, None, context_id=context_id, task_id=task_id)
                                )

                                if reason_tool_name:
                                    default_reminder = (
                                        f"Ты не вызвал tool '{exit_tool_name}' для завершения. "
                                        f"Сначала вызови {reason_tool_name}(thought='...') для рассуждения, "
                                        f"затем {exit_tool_name}(answer='твой финальный ответ') "
                                        f"чтобы завершить работу."
                                    )
                                else:
                                    default_reminder = (
                                        f"Ты не вызвал tool '{exit_tool_name}' для завершения. "
                                        f"Используй {exit_tool_name}(answer='твой финальный ответ') "
                                        f"чтобы завершить работу."
                                    )
                                state.messages.append(
                                    new_system_message(
                                        reminder_message or default_reminder,
                                        context_id=context_id,
                                        task_id=task_id,
                                        source_node_id=sid,
                                    )
                                )
                                await self._checkpoint_state(state)
                if not final_response:
                    error_payload: JsonObject = {
                        "node_id": sid,
                        "max_iterations": max_iterations,
                        "iterations_used": iteration,
                        "loop_mode": loop_mode.value,
                    }
                    if iteration >= max_iterations:
                        raise FlowExecutionError(
                            message=(
                                f"LLM node '{llm_node_label}' reached max_iterations={max_iterations} "
                                f"without final response (iterations_used={iteration})"
                            ),
                            payload=error_payload,
                        )
                    raise FlowExecutionError(
                        message=(
                            f"LLM node '{llm_node_label}' returned empty final response "
                            f"after {iteration} iteration(s)"
                        ),
                        payload=error_payload,
                    )
            except FlowInterrupt:
                await self._checkpoint_state(state)
                tracer.record_state_snapshot(llm_node_span, state.model_dump(mode="json", exclude_none=False))
                raise
            finally:
                if iteration > 0:
                    logger.info(
                        EVENT_FLOW_REACT_COMPLETED,
                        **{
                            LOG_FLOW_REACT_ITERATIONS: iteration,
                            LOG_FLOW_REACT_MAX_ITERATIONS: max_iterations,
                            LOG_FLOW_REACT_INTERRUPTED: bool(state.interrupt),
                            LOG_TASK_ID: task_id,
                            LOG_FLOW_ID: state.session_flow_id,
                            "llm_node_label": llm_node_label,
                        },
                    )
                if final_response:
                    state.response = final_response
                    tracer.record_state_snapshot(llm_node_span, state.model_dump(mode="json", exclude_none=False))
                    await self._close_context_memory_window(state)
                    await self._checkpoint_state(state)

    async def _with_vision_file_parts(
        self,
        state: ExecutionState,
        messages: list[Message],
    ) -> list[Message]:
        """``llm_vision``: байты image-файлов ``state.files`` — Parts последнего user-сообщения.

        Инжекция только в исходящий вызов, в ``state.messages`` сырьё не пишется
        (в durable state живут FileRef'ы); байты кешируются на прогон ноды.
        """
        image_refs = [
            ref
            for ref in state.files
            if ref.file_id is not None
            and bool(ref.file_id.strip())
            and ref.content_type.startswith("image/")
        ]
        if not image_refs:
            return messages
        last_user_index = -1
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].role == ROLE_USER:
                last_user_index = index
                break
        if last_user_index < 0:
            return messages
        vision_message = Message()
        vision_message.CopyFrom(messages[last_user_index])
        for ref in image_refs:
            if ref.file_id is None:
                continue
            vision_message.parts.append(
                Part(
                    raw=await self._vision_file_bytes(ref.file_id),
                    media_type=ref.content_type,
                    filename=ref.original_name or ref.file_id,
                )
            )
        injected = list(messages)
        injected[last_user_index] = vision_message
        return injected

    async def _vision_file_bytes(self, file_id: str) -> bytes:
        cached = self._vision_bytes.get(file_id)
        if cached is not None:
            return cached
        record = await FileRecord.get(file_id)
        if record is None:
            raise ValueError(f"llm_vision: file not found: {file_id}")
        handle = await FileGate().open_record(
            record, SystemPrincipal(company_id=record.company_id or "")
        )
        data = await handle.read_bytes()
        self._vision_bytes[file_id] = data
        return data

    def _resolve_llm_client(
        self,
        state: ExecutionState,
        *,
        effective_llm: EffectiveLLMConfig,
        mock_llm_client: MockLLM | None = None,
    ) -> tuple[LLMClient | MockLLM, int | None]:
        llm_config = effective_llm.config
        max_tok = llm_config.max_tokens
        if mock_llm_client is not None:
            return mock_llm_client, max_tok
        llm = create_llm_client_from_call_config(
            llm_config,
            variables=state.variables,
            fallback_models=llm_config.fallback_models,
            cost_origin=effective_llm.cost_origin,
            billing_resource_name=effective_llm.billing_resource_name,
        )
        return llm, max_tok

    async def _call_llm(
        self,
        llm: LLMClient | MockLLM,
        max_tok: int | None,
        messages: list[Message],
        tools: list[OpenAIToolSchema] | None,
        context_id: str,
        task_id: str,
        response_format: JsonObject | None,
        state: ExecutionState,
        *,
        iteration: int,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Вызывает LLM — ТОЛЬКО STREAM.

        При LLMStreamIdleTimeoutError автоматически делает retry
        (до MAX_STREAM_IDLE_RETRIES раз). Это прозрачно для вызывающего
        кода — он получает чанки, как если бы retry не было.
        """
        async def _stream_cancel_poll() -> bool:
            token = get_cancellation_token()
            if token is None:
                return False
            return await token.is_cancelled()

        if isinstance(llm, MockLLM):
            async for event in llm.stream(
                messages=messages,
                tools=tools,
                response_format=response_format,
                task_id=task_id,
                context_id=context_id,
                max_tokens=max_tok,
                llm_context=self.llm_context_policy or self.node_config.llm_context or {},
                llm_context_blocks=self._agent_skill_context_blocks(),
                llm_context_source_registry=self.llm_context_source_registry,
                stream_cancel_poll=_stream_cancel_poll,
            ):
                await check_cancellation(state)
                yield event
            return

        for attempt in range(1, self.MAX_STREAM_IDLE_RETRIES + 2):  # +2: 1 исходная + N повторов
            input_payload = require_json_object(
                {
                    "node_id": self._source_node_id(),
                    "iteration": iteration,
                    "attempt": attempt,
                    "messages": self._messages_to_dict(messages),
                    "tools": [
                        require_json_object(tool, "llm.tool_schema")
                        for tool in tools or []
                    ],
                    "response_format": response_format,
                    "max_tokens": max_tok,
                },
                "llm.activity_input",
            )
            branch_id = await self._active_execution_branch_id(state)
            activity_id = (
                f"{state.session_id}:{branch_id}:node:{self._source_node_id()}:"
                + f"llm:iteration:{iteration}:attempt:{attempt}:"
                + f"input:{hash_state_json(input_payload)}"
            )
            runtime = self.workflow_runtime
            scheduled_result = await runtime.record_activity_scheduled(
                session_id=state.session_id,
                activity_id=activity_id,
                activity_type="llm",
                input_payload=input_payload,
                node_id=self._source_node_id(),
                idempotency_key=activity_id,
                side_effect_policy=SideEffectPolicy.idempotent,
            )
            if scheduled_result is None:
                started = await runtime.record_activity_started(
                    activity_id=activity_id,
                )
                if not started:
                    raise RuntimeError(f"Failed to mark LLM activity as started: {activity_id!r}")
            try:
                async for event in llm.stream(
                    messages=messages,
                    tools=tools,
                    response_format=response_format,
                    task_id=task_id,
                    context_id=context_id,
                    max_tokens=max_tok,
                    llm_context=self.llm_context_policy or self.node_config.llm_context or {},
                    llm_context_blocks=self._agent_skill_context_blocks(),
                    llm_context_source_registry=self.llm_context_source_registry,
                    stream_cancel_poll=_stream_cancel_poll,
                ):
                    await check_cancellation(state)
                    yield event
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    result_json={"completed": True},
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark LLM activity as completed: {activity_id!r}")
                return  # Стрим завершился нормально
            except LLMStreamUserCancelledError:
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    error="LLMStreamUserCancelledError",
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark LLM activity as failed: {activity_id!r}")
                tok = get_cancellation_token()
                raise FlowCancelled(tok.task_id if tok is not None else task_id)
            except LLMStreamIdleTimeoutError as e:
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    error=str(e),
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark LLM activity as failed: {activity_id!r}")
                if attempt <= self.MAX_STREAM_IDLE_RETRIES:
                    logger.warning(
                        "llm.stream.idle_timeout_retry",
                        attempt=attempt,
                        max_attempts=self.MAX_STREAM_IDLE_RETRIES + 1,
                        idle_seconds=e.idle_seconds,
                        chunks_received=e.chunks_received,
                    )
                    continue
                # Все retry исчерпаны
                logger.error(
                    "llm.stream.idle_timeout_exhausted",
                    attempt=attempt,
                    idle_seconds=e.idle_seconds,
                    chunks_received=e.chunks_received,
                )
                raise

    def _agent_skill_context_blocks(self) -> list[LLMContextBlock] | None:
        if self.agent_skill_host is None:
            return None
        if not self.agent_skill_host.context_blocks:
            return None
        return list(self.agent_skill_host.context_blocks)

    async def _flush_pending_agent_skill_tools(self) -> None:
        host = self.agent_skill_host
        if host is None or not host.pending_tool_refs:
            return
        pending = list(host.pending_tool_refs)
        host.pending_tool_refs.clear()
        new_tools = await self.tool_registry.create_tools(pending)
        self.tools = merge_tools_by_name(self.tools, new_tools)

    async def _execute_tools_parallel(
        self,
        tool_calls: list[LLMToolCall],
        state: ExecutionState,
        trace_ctx: TraceContext | None = None,
        emitter: BaseEmitter | None = None,
    ) -> list[dict[str, str]]:
        """
        Выполняет tools ПАРАЛЛЕЛЬНО через asyncio.gather.

        Каждый tool получает копию state.
        Результаты мержатся: messages extend, остальное - кто последний.
        """
        if len(tool_calls) == 1:
            # Один tool - выполняем напрямую без копирования
            return await self._execute_single_tool(tool_calls[0], state, trace_ctx, emitter)

        # Несколько tools - параллельное выполнение
        original_msg_count = len(state.messages)
        original_reasoning_count = len(state.reasoning_history)

        # Создаем копии state для каждого tool
        state_copies = [state.runtime_copy() for _ in tool_calls]

        # Запускаем все tools параллельно
        tasks = [
            self._execute_single_tool(tc, state_copy, trace_ctx, emitter)
            for tc, state_copy in zip(tool_calls, state_copies)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Собираем результаты и мержим state
        tool_results: list[dict[str, str]] = []
        deferred_interrupt: FlowInterrupt | None = None
        deferred_error: Exception | None = None
        for tc, result, state_copy in zip(tool_calls, results, state_copies):
            tool_name = tc.name
            tool_call_id = tc.id

            if isinstance(result, BaseException):
                if isinstance(result, FlowCancelled):
                    raise result
                if not isinstance(result, Exception):
                    raise result
                if isinstance(result, FlowInterrupt):
                    result.tool_call = result.tool_call or tc
                    deferred_interrupt = deferred_interrupt or result
                    continue
                if isinstance(result, ToolExecutionError):
                    deferred_error = deferred_error or result
                    continue
                enabled, allow_types = self._exception_policy_from_node_config()
                if should_absorb_exception(
                    result, enabled=enabled, allow_types=allow_types
                ):
                    self._record_tool_exception(
                        state, tool_name, tool_call_id, result
                    )
                    tool_results.append(
                        {
                            "tool_call_id": tool_call_id,
                            "content": self._format_tool_error_content(
                                tool_name, result
                            ),
                        }
                    )
                    continue
                logger.error("flows.llm.tool_failed", tool_name=tool_name, result=result)
                deferred_error = deferred_error or ToolExecutionError(tool_name, result)
                continue

            # Мержим state: messages extend, остальное перезаписываем
            new_messages = state_copy.messages[original_msg_count:]
            state.messages.extend(new_messages)

            # tool_results — мержим (не перезаписываем!)
            state.tool_results.update(state_copy.tool_results)

            new_reasoning_entries = state_copy.reasoning_history[original_reasoning_count:]
            if new_reasoning_entries:
                state.reasoning_history.extend(new_reasoning_entries)
                state.pending_reasoning = new_reasoning_entries[-1]

            for field in USER_TOOL_PARALLEL_STATE_MERGE_FIELDS:
                if field == "variables":
                    merged_vars = dict(state.variables)
                    merged_vars.update(state_copy.variables)
                    state.variables = merged_vars
                    continue
                if field == "content":
                    value = state_copy.content
                    if value is not None:
                        state.content = value
                    continue
                if field == "response":
                    value = state_copy.response
                    if value is not None:
                        state.response = value
                    continue
                if field == "result":
                    value = state_copy.result
                    if value is not None:
                        state.result = value
                    continue
                if field == "validation":
                    value = state_copy.validation
                    if value is not None:
                        state.validation = value
                    continue
                if field == "files":
                    files = state_copy.files
                    if files:
                        state.files = files
                    continue
                raise ValueError(f"Unsupported tool parallel merge field: {field}")

            extra_src = require_json_object(
                state_copy.__pydantic_extra__ or {},
                "state.extra",
            )
            for ek, ev in extra_src.items():
                if ek in FROZEN_STATE_FIELDS:
                    continue
                if ev is not None:
                    state[ek] = ev

            tool_results.extend(result)

        if deferred_interrupt is not None:
            raise deferred_interrupt
        if deferred_error is not None:
            raise deferred_error

        return tool_results

    async def _execute_single_tool(
        self,
        tc: LLMToolCall,
        state: ExecutionState,
        trace_ctx: TraceContext | None = None,
        emitter: BaseEmitter | None = None,
    ) -> list[dict[str, str]]:
        """Выполняет один tool."""
        tracer = get_tracer()
        tool_name = tc.name
        tool_args: ToolArguments = tc.arguments
        tool_call_id = tc.id

        tool = self._resolve_tool_by_call_name(tool_name)
        if not tool:
            not_found = RuntimeError(
                "Tool not found. Flow must be fully inline with all tools loaded."
            )
            enabled, allow_types = self._exception_policy_from_node_config()
            if should_absorb_exception(
                not_found, enabled=enabled, allow_types=allow_types
            ):
                self._record_tool_exception(
                    state, tool_name, tool_call_id, not_found
                )
                return [
                    {
                        "tool_call_id": tool_call_id,
                        "content": self._format_tool_error_content(
                            tool_name, not_found
                        ),
                    }
                ]
            raise ToolExecutionError(tool_name, not_found)
        tool_name = tool.name

        nested_flow_tool = tool.is_nested_flow_tool
        input_payload = require_json_object(
            {
                "tool_name": tool_name,
                "arguments": require_json_object(tool_args, "tool_args"),
            },
            "activity.input_payload",
        )
        branch_id = await self._active_execution_branch_id(state)
        activity_id = (
            f"{state.session_id}:{branch_id}:node:{self._source_node_id()}:"
            + f"tool:{tool_call_id}:input:{hash_state_json(input_payload)}"
        )
        idempotency_key = activity_id
        runtime = self.workflow_runtime
        completed = await runtime.get_completed_activity_result(
            session_id=state.session_id,
            activity_id=activity_id,
            idempotency_key=idempotency_key,
            input_payload=input_payload,
        )
        if completed is not None:
            delta_raw = completed.get("state_delta")
            if isinstance(delta_raw, dict):
                replayed_state = apply_state_delta(
                    state,
                    ExecutionStateDelta.model_validate(delta_raw),
                )
                _copy_state_projection(state, replayed_state)
            result_text = str(completed.get("result", ""))
            logger.info(
                "tool.activity_replayed",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
            return [
                {
                    "tool_call_id": tool_call_id,
                    "content": result_text,
                }
            ]

        scheduled_result = await runtime.record_activity_scheduled(
            session_id=state.session_id,
            activity_id=activity_id,
            activity_type="tool",
            input_payload=input_payload,
            node_id=self._source_node_id(),
            tool_call_id=tool_call_id,
            idempotency_key=idempotency_key,
            side_effect_policy=SideEffectPolicy.non_idempotent,
        )
        if scheduled_result is not None:
            delta_raw = scheduled_result.get("state_delta")
            if isinstance(delta_raw, dict):
                replayed_state = apply_state_delta(
                    state,
                    ExecutionStateDelta.model_validate(delta_raw),
                )
                _copy_state_projection(state, replayed_state)
            return [
                {
                    "tool_call_id": tool_call_id,
                    "content": str(scheduled_result.get("result", "")),
                }
            ]
        started = await runtime.record_activity_started(activity_id=activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark tool activity as started: {activity_id!r}")

        async with tracer.tool_call_span(
            tool_name, tool_call_id, tool_args, nested_flow_tool, trace_ctx=trace_ctx
        ) as tool_span:
            tool_start = time.time()
            before_tool_state = ExecutionState.model_validate(
                state.model_dump(mode="python", exclude_none=False)
            )

            logger.info("flows.llm.tool_executing", tool_name=tool_name)
            try:
                reasoning_count_before = len(state.reasoning_history)
                # Mock Control: если tool замокан, берём следующий ответ из его
                # очереди вместо реального вызова; очередь исчерпана → MockControlError.
                mock_tool_result = await resolve_tool_mock_result(
                    self.redis_client, state.session_id, tool_name
                )
                if mock_tool_result is not None:
                    result = mock_tool_result
                else:
                    with active_tool_call_context(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        node_id=self._source_node_id(),
                        state=state,
                        emitter=emitter,
                    ):
                        if self.agent_skill_host is not None:
                            with agent_skill_runtime_host_scope(self.agent_skill_host):
                                result = await tool.run(tool_args, state)
                        else:
                            result = await tool.run(tool_args, state)
                    await self._flush_pending_agent_skill_tools()
                self._record_reason_tool_call(
                    tool=tool,
                    tool_args=tool_args,
                    state=state,
                    reasoning_count_before=reasoning_count_before,
                )
                state.tool_results[tool_name] = result

                tool_duration = (time.time() - tool_start) * 1000
                tracer.record_tool_result(tool_span, result, tool_duration)
                tracer.record_state_snapshot(tool_span, state.model_dump(mode="json", exclude_none=False))
                state_delta = build_state_delta(before_tool_state, state)
                tool_result_content = _format_tool_result_content(result)
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    result_json={
                        "result": tool_result_content,
                        "state_delta": state_delta.model_dump(
                            mode="json",
                            exclude_none=False,
                        ),
                    },
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark tool activity as completed: {activity_id!r}")

                return [
                    {
                        "tool_call_id": tool_call_id,
                        "content": tool_result_content,
                    }
                ]
            except FlowInterrupt:
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    error="FlowInterrupt",
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark tool activity as failed: {activity_id!r}")
                raise
            except Exception as e:
                tool_duration = (time.time() - tool_start) * 1000
                tracer.record_tool_result(tool_span, None, tool_duration, error=str(e))
                logger.error("flows.llm.tool_error", tool_name=tool_name, error=str(e))
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    error=str(e),
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark tool activity as failed: {activity_id!r}")
                enabled, allow_types = self._exception_policy_from_node_config()
                absorb = is_tool_arg_validation_error(e) or should_absorb_exception(
                    e, enabled=enabled, allow_types=allow_types
                )
                if absorb:
                    self._record_tool_exception(
                        state, tool_name, tool_call_id, e
                    )
                    return [
                        {
                            "tool_call_id": tool_call_id,
                            "content": self._format_tool_error_content(
                                tool_name, e
                            ),
                        }
                    ]
                raise ToolExecutionError(tool_name, e)

    def _record_reason_tool_call(
        self,
        *,
        tool: BaseTool,
        tool_args: ToolArguments,
        state: ExecutionState,
        reasoning_count_before: int,
    ) -> None:
        if tool.react_role != ReactToolRole.REASON:
            return
        if len(state.reasoning_history) > reasoning_count_before:
            state.pending_reasoning = state.reasoning_history[-1]
            return
        reasoning_entry = require_json_object(
            dict(tool_args),
            f"tool.{tool.name}.reasoning_entry",
        )
        state.reasoning_history.append(reasoning_entry)
        state.pending_reasoning = reasoning_entry

    async def _render_prompt(self, state: ExecutionState) -> str:
        """Рендерит промпт с переменными и сохраняет в историю."""
        prompt_template = self.prompt
        flow_variables = self.get_variables(state)
        # Поля интерфейса — обычные пользовательские поля state: {email}, {lead.headcount}.
        # Они перекрывают одноимённые переменные flow; локальные переменные ноды — выше всех.
        variables: JsonObject = {
            **flow_variables,
            **state.json_extra(),
            **(self.node_config.local_variables if self.node_config else {}),
        }

        if self.llm_node:
            prompt_template, variables = await self.llm_node.before_prompt_render(
                prompt_template, state, variables
            )

        resolved_vars = require_json_object(
            VariableResolver.resolve_all(local_vars=variables),
            "prompt.variables",
        )

        tracer = get_tracer()
        trace_ctx = _get_trace_ctx_from_state()
        node_id = self.node_config.node_id if self.node_config else "unknown"

        async with tracer.prompt_build_span(
            node_id=node_id,
            template=prompt_template,
            variables=resolved_vars,
            trace_ctx=trace_ctx,
        ) as span:
            rendered_prompt = VariableResolver.render_template(prompt_template, local_vars=variables)

            if self.llm_node:
                rendered_prompt = await self.llm_node.after_prompt_render(rendered_prompt, state)

            tracer.record_prompt_result(span, rendered_prompt)
            self._save_prompt_to_history(state, prompt_template, rendered_prompt, resolved_vars, node_id)

        return rendered_prompt

    def _save_prompt_to_history(
        self,
        state: ExecutionState,
        template: str,
        rendered: str,
        variables: JsonObject,
        node_id: str,
    ) -> None:
        """Сохраняет промпт в историю если он изменился."""
        prompt_hash = hashlib.md5(rendered.encode()).hexdigest()

        if state.prompt_history:
            last = state.prompt_history[-1]
            if last.prompt_hash == prompt_hash:
                return

        safe_vars: JsonObject = {
            k: v for k, v in variables.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }

        item = PromptHistoryItem(
            prompt_hash=prompt_hash,
            prompt=rendered,
            template=template,
            variables_used=safe_vars,
            node_id=node_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        state.prompt_history.append(item)

    def _build_tools_schema(self) -> list[OpenAIToolSchema]:
        """Строит схему инструментов для LLM."""
        schema: list[OpenAIToolSchema] = []
        for tool in self.tools:
            schema.append(tool.to_openai_schema())
        return schema
