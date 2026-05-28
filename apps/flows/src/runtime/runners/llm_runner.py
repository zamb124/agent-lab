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
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import ClassVar, cast, override

from a2a.types import (
    Message,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import (
    ExecutionStateDelta,
    SideEffectPolicy,
    WorkflowEventType,
    apply_state_delta,
    build_state_delta,
    hash_state_json,
)
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
from apps.flows.src.runtime.effective_llm_config import (
    EffectiveLLMConfig,
    resolve_effective_llm_config_for_node,
)
from apps.flows.src.runtime.exception_policy import should_absorb_exception
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.llm_config_params import (
    client_kwargs_from_llm_config,
    split_llm_config_for_client,
)
from apps.flows.src.runtime.llm_context_memory import (
    RuntimeMemoryWriteCommand,
    RuntimeMemoryWriteResult,
    apply_runtime_memory_cursor_advance,
    apply_runtime_memory_write_result,
    build_state_messages_memory_close_decision,
    write_runtime_memory_episode,
)
from apps.flows.src.runtime.tool_call_context import active_tool_call_context
from apps.flows.src.state.cancellation import (
    FlowCancelled,
    check_cancellation,
    get_cancellation_token,
)
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming import BaseEmitter, Emitter
from apps.flows.src.streaming.ui_events import emit_pending_ui_events
from apps.flows.src.tools.base import BaseTool, OpenAIToolSchema, ToolArguments, sanitize_tool_name
from apps.flows.src.variables import VariableResolver
from core.billing import get_cbr_usd_to_rub_rate
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm import (
    LLMClient,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
    LLMToolCall,
    MockLLM,
    StreamEvent,
    get_llm_for_state,
    should_use_platform_default_free_pool,
)
from core.company_ai import COST_ORIGIN_COMPANY
from core.config import get_settings
from core.config.testing import is_testing
from core.context import get_context
from core.errors import FlowExecutionError, ToolExecutionError
from core.llm_context import (
    LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION,
    LLMContextProfile,
    LLMContextSourceRegistry,
)
from core.logging import get_logger
from core.state import (
    ExecutionExceptionRecord,
    ExecutionState,
    InterruptPathItem,
    PromptHistoryItem,
)
from core.state.mutation_policy import FROZEN_STATE_FIELDS, USER_TOOL_PARALLEL_STATE_MERGE_FIELDS
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
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

from .base_runner import BaseLlmNodeRunner, LlmNodeRunnerHost

logger = get_logger(__name__)

def _get_trace_ctx_from_state() -> TraceContext | None:
    """Получает TraceContext из ContextVar worker'а."""
    trace_data = get_current_trace_context()
    if trace_data:
        return TraceContext.from_dict(trace_data)
    return None


def _get_message_metadata(msg: Message) -> JsonObject:
    """Получает metadata из Message."""
    raw_metadata = msg.metadata
    if raw_metadata is None:
        return {}
    return require_json_object(raw_metadata, "message.metadata")


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
            target[field_name] = data[field_name]
    extras = require_json_object(source.__pydantic_extra__ or {}, "state.extra")
    for key, value in extras.items():
        if key not in FROZEN_STATE_FIELDS:
            target[key] = value


class LlmNodeRunner(BaseLlmNodeRunner):
    """
    Runner для LLM-нод (ReAct цикл).
    Stream-first: ТОЛЬКО STREAM!
    """

    MAX_ITERATIONS: ClassVar[int] = 10
    MAX_STREAM_IDLE_RETRIES: ClassVar[int] = 4  # При idle timeout 10с — макс 50с ожидания (5 попыток × 10с)

    def __init__(
        self,
        node_config: NodeConfig,
        tools: list[BaseTool],
        llm: LLMClient | MockLLM | None,
        prompt: str,
        llm_node: LlmNodeRunnerHost | None = None,
        *,
        container: FlowRuntimeContainer,
        llm_context_policy: LLMContextProfile | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ):
        super().__init__(
            node_config=node_config,
            tools=tools,
            llm=llm,
            prompt=prompt,
            llm_node=llm_node,
        )
        self.container: FlowRuntimeContainer = container
        self.llm_context_policy: LLMContextProfile | None = llm_context_policy
        self.llm_context_source_registry: LLMContextSourceRegistry | None = llm_context_source_registry
        for tool in self.tools:
            tool.container = container

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
        runtime = self.container.workflow_runtime
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
                    store=self.container.llm_context_memory_store,
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
        return await self.container.text_transform_service.summarize(
            text,
            max_output_tokens=700,
            instruction=LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION,
            provider=llm_config.provider,
            model=llm_config.model,
        )

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
            return self.llm_node.get_filtered_messages(state)
        return list(state.messages)

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
            emitter = Emitter(self.container.redis_client, state)

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
            state.messages.append(
                new_user_message(
                    user_content, sid, context_id=context_id, task_id=task_id
                )
            )
            await self._checkpoint_state(state)

        async for event in self._react_loop(
            state, llm_node_label, context_id, task_id, emitter
        ):
            yield event

    def _messages_to_dict(self, messages: list[Message]) -> list[JsonObject]:
        """Конвертирует Message объекты в dict для трейсинга."""
        result: list[JsonObject] = []
        for msg in messages:
            result.append(require_json_object(msg.model_dump(mode="json"), "llm.message"))
        return result

    async def _active_execution_branch_id(self, state: ExecutionState) -> str:
        position = await self.container.workflow_runtime.get_active_execution_position(
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
        self, messages: list[Message], tool_name: str
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
            f"Resume: type={call_type}, id={call_id}, tool_call_id={tool_call_id}, "
            + f"path_len={len(interrupt_path)}, answer={user_answer[:50]}..."
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
            raise ValueError("Контекст с active_company обязателен для LLM-ноды")
        if not str(actx.user.user_id).strip():
            raise ValueError("Контекст с user обязателен для LLM-ноды (биллинг и уведомления)")
        container = self.container
        allow_platform_paid_fallback = True
        byok_override = effective_llm.cost_origin == COST_ORIGIN_COMPANY
        (
            billing_model,
            _billing_temp,
            billing_provider,
            billing_api_key,
            billing_base_url,
            _billing_max_tok,
            billing_folder_id,
            _billing_fallback_models,
        ) = split_llm_config_for_client(llm_config)
        uses_platform_free_pool = should_use_platform_default_free_pool(
            model=billing_model,
            provider=billing_provider,
            api_key=billing_api_key,
            base_url=billing_base_url,
            folder_id=billing_folder_id,
            settings=get_settings(),
        )
        mock_llm_call = (
            is_testing()
            or str(billing_model or "").startswith("mock-")
            or str(billing_provider or "") == "mock"
        )
        if not byok_override and not mock_llm_call:
            if uses_platform_free_pool:
                allow_platform_paid_fallback = (
                    await container.billing_service.company_may_incur_billable_operation_charge(
                        actx.active_company.company_id
                    )
                )
                if not allow_platform_paid_fallback:
                    logger.info(
                        "llm.default_free_pool_paid_fallback_disabled",
                        company_id=actx.active_company.company_id,
                        node_id=self.node_config.node_id if self.node_config else None,
                    )
            else:
                await container.billing_service.require_balance_for_billable_operation(
                    actx.active_company.company_id,
                    str(actx.user.user_id).strip(),
                    operation_code=BALANCE_BLOCK_OPERATION_LLM,
                    notification_service="flows",
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
                f"[llm_node:{llm_node_label}] Structured Output режим, schema keys: {schema_keys}"
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

                    logger.debug(f"[llm_node:{llm_node_label}] ReAct iteration {iteration} (streaming)")

                    messages = self._messages_for_llm_context(state)

                    async with tracer.react_iteration_span(
                        iteration, llm_node_label, trace_ctx=trace_ctx
                    ):
                        llm_messages = [system_msg] + messages
                        content = ""
                        tool_calls: list[LLMToolCall] | None = None
                        had_reasoning_event = False
                        llm_start = time.time()
                        input_tokens = 0
                        output_tokens = 0
                        provider_reported_cost: float | None = None
                        provider_upstream_inference_cost: float | None = None
                        settlement_quantity_rub: int | None = None
                        resolved_llm_model: str | None = None
                        resolved_llm_provider: str | None = None
                        resolved_llm_source: str | None = None
                        llm_context_trace: JsonObject | None = None

                        llm, max_tok = self._resolve_llm_client(
                            state,
                            effective_llm=effective_llm,
                            allow_platform_paid_fallback=allow_platform_paid_fallback,
                        )
                        llm_provider = llm.llm_provider
                        billing_res = effective_llm.billing_resource_name

                        async with tracer.llm_call_span(
                            model,
                            len(llm_messages),
                            len(tools_schema) if tools_schema else 0,
                            trace_ctx=trace_ctx,
                            llm_provider=llm_provider,
                        ) as llm_span:
                            llm_messages_for_trace = self._messages_to_dict(llm_messages)
                            tracer.record_llm_request(llm_span, llm_messages_for_trace, tools_schema, response_format)

                            try:
                                async for event in self._call_llm(
                                    llm,
                                    max_tok,
                                    llm_messages,
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
                                                if isinstance(part.root, TextPart):
                                                    content += part.root.text
                                            if loop_mode == ReactLoopMode.EXPLICIT:
                                                should_yield = False

                                    if should_yield:
                                        await emitter.emit(event)
                                        yield event

                                    if isinstance(event, TaskStatusUpdateEvent):
                                        if event.status.message and event.status.message.metadata:
                                            md = require_json_object(
                                                event.status.message.metadata,
                                                "llm.event.metadata",
                                            )
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
                                            context_raw = md.get("llm_context")
                                            if isinstance(context_raw, dict):
                                                llm_context_trace = require_json_object(
                                                    context_raw,
                                                    "llm.event.metadata.llm_context",
                                                )
                                            usage_raw = md.get("usage")
                                            if isinstance(usage_raw, dict):
                                                usage = require_json_object(usage_raw, "llm.event.metadata.usage")
                                                raw_input_tokens = usage.get("input_tokens", 0)
                                                raw_output_tokens = usage.get("output_tokens", 0)
                                                if isinstance(raw_input_tokens, bool) or not isinstance(raw_input_tokens, int):
                                                    raise ValueError("usage.input_tokens must be an integer")
                                                if isinstance(raw_output_tokens, bool) or not isinstance(raw_output_tokens, int):
                                                    raise ValueError("usage.output_tokens must be an integer")
                                                input_tokens = raw_input_tokens
                                                output_tokens = raw_output_tokens
                                                prc = usage.get("provider_reported_cost")
                                                if isinstance(prc, (int, float)):
                                                    provider_reported_cost = float(prc)
                                                puc = usage.get("provider_upstream_inference_cost")
                                                if isinstance(puc, (int, float)):
                                                    provider_upstream_inference_cost = float(puc)
                            except FlowCancelled:
                                self._append_interrupted_stream_assistant(
                                    state,
                                    content,
                                    sid=sid,
                                    context_id=context_id,
                                    task_id=task_id,
                                )
                                raise

                            if (
                                (resolved_llm_provider or llm_provider) == "openrouter"
                                and provider_reported_cost is not None
                                and provider_reported_cost > 0
                            ):
                                rate = get_cbr_usd_to_rub_rate(
                                    fallback=get_settings().billing.usd_to_rub_rate
                                )
                                rub = int(round(provider_reported_cost * rate))
                                if rub >= 1:
                                    settlement_quantity_rub = rub

                            llm_duration = (time.time() - llm_start) * 1000
                            if resolved_llm_model:
                                logger.info(
                                    "llm.call_resolved",
                                    requested_model=model,
                                    provider=resolved_llm_provider or llm_provider,
                                    model=resolved_llm_model,
                                    source=resolved_llm_source,
                                )
                            tracer.record_llm_response(
                                llm_span,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                has_tool_calls=bool(tool_calls),
                                duration_ms=llm_duration,
                                response_content=content,
                                tool_calls=[
                                    require_json_object(
                                        tool_call.model_dump(mode="json", exclude_none=True),
                                        "llm.tool_call",
                                    )
                                    for tool_call in tool_calls
                                ] if tool_calls else None,
                                llm_provider=resolved_llm_provider or llm_provider,
                                llm_model=resolved_llm_model,
                                candidate_source=resolved_llm_source,
                                provider_reported_cost=provider_reported_cost,
                                provider_upstream_inference_cost=provider_upstream_inference_cost,
                                settlement_quantity_rub=settlement_quantity_rub,
                                billing_resource_name=billing_res,
                                llm_context=llm_context_trace,
                            )

                        if tool_calls:
                            tool_names = [tc.name for tc in tool_calls]
                            logger.info(f"[llm_node:{llm_node_label}] Вызов tools: {tool_names}")

                            exit_call = self._find_exit_tool_call(tool_calls, exit_tool_name)

                            if exit_call and loop_mode == ReactLoopMode.EXPLICIT:
                                exit_args = exit_call.arguments
                                exit_tool = next(t for t in self.tools if t.name == exit_tool_name)
                                result = await exit_tool.run(exit_args, state)
                                final_response = str(result) if not isinstance(result, str) else result

                                logger.info(
                                    f"[llm_node:{llm_node_label}] Exit tool '{exit_tool_name}' вызван, завершение"
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
                                await self._emit_pending_ui_events(emitter, state)

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
                                    await self._emit_pending_ui_events(emitter, state)

                                pending_reasoning = state.pending_reasoning
                                if pending_reasoning:
                                    await emitter.emit_reasoning(
                                        json.dumps(pending_reasoning, ensure_ascii=False)
                                    )
                                    state.pending_reasoning = None

                                await self._emit_pending_ui_events(emitter, state)
                                await self._checkpoint_state(state)

                            except FlowInterrupt as e:
                                interrupted_tc = e.tool_call or tool_calls[0]
                                logger.info(
                                    f"[llm_node:{llm_node_label}] Interrupt: tool={interrupted_tc.name}"
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
                                    parsed_output = require_json_value(
                                        cast(JsonValue, json.loads(content)),
                                        "llm.structured_output",
                                    )
                                    state.set_structured_output_result(parsed_output)
                                    final_response = content
                                    parsed_output_keys: list[str] = (
                                        list(parsed_output.keys())
                                        if isinstance(parsed_output, dict)
                                        else []
                                    )
                                    logger.info(
                                        f"[llm_node:{llm_node_label}] Structured Output получен: {parsed_output_keys or type(parsed_output)}"
                                    )
                                except json.JSONDecodeError as e:
                                    logger.error(f"[llm_node:{llm_node_label}] Ошибка парсинга structured output: {e}")
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
                                    f"[llm_node:{llm_node_label}] Финальный ответ: {final_response[:100]}..."
                                )
                                state.messages.append(
                                    new_assistant_message(
                                        final_response, sid, None, context_id=context_id, task_id=task_id
                                    )
                                )
                                InterruptManager.clear_interrupt_path(state)
                                await self._checkpoint_state(state)
                                break
                            else:
                                if not strict:
                                    final_response = content
                                    logger.info(
                                        f"[llm_node:{llm_node_label}] EXPLICIT non-strict: текст принят как ответ"
                                    )
                                    state.messages.append(
                                        new_assistant_message(
                                            final_response, sid, None, context_id=context_id, task_id=task_id
                                        )
                                    )
                                    InterruptManager.clear_interrupt_path(state)
                                    await self._checkpoint_state(state)
                                    break

                                logger.warning(
                                    f"[llm_node:{llm_node_label}] EXPLICIT strict: LLM вернул текст без "
                                    + f"exit_tool '{exit_tool_name}', добавляем reminder"
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
                    raise FlowExecutionError(
                        message=(
                            f"LLM node '{llm_node_label}' reached max_iterations={max_iterations} "
                            "without final response"
                        ),
                        payload={
                            "node_id": sid,
                            "max_iterations": max_iterations,
                            "loop_mode": loop_mode.value,
                        },
                    )
            except FlowInterrupt:
                await self._checkpoint_state(state)
                tracer.record_state_snapshot(llm_node_span, state)
                raise
            finally:
                if final_response:
                    state.response = final_response
                    tracer.record_state_snapshot(llm_node_span, state)
                    await self._close_context_memory_window(state)
                    await self._checkpoint_state(state)

    def _resolve_llm_client(
        self,
        state: ExecutionState,
        *,
        effective_llm: EffectiveLLMConfig,
        allow_platform_paid_fallback: bool = True,
    ) -> tuple[LLMClient | MockLLM, int | None]:
        llm_config = effective_llm.config
        max_tok = llm_config.max_tokens
        client_kwargs = client_kwargs_from_llm_config(llm_config, state)
        llm = get_llm_for_state(
            state,
            **client_kwargs,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
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
            runtime = self.container.workflow_runtime
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
                        "LLM stream idle timeout (attempt %d/%d), retrying: "
                        + "idle=%.1fs, chunks=%d",
                        attempt,
                        self.MAX_STREAM_IDLE_RETRIES + 1,
                        e.idle_seconds,
                        e.chunks_received,
                    )
                    continue
                # Все retry исчерпаны
                logger.error(
                    "LLM stream idle timeout after %d attempts, giving up: "
                    + "idle=%.1fs, chunks=%d",
                    attempt, e.idle_seconds, e.chunks_received,
                )
                raise

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
                logger.error(f"Tool {tool_name} failed: {result}")
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
        runtime = self.container.workflow_runtime
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

            logger.info(f"Выполняю tool: {tool_name}")
            try:
                reasoning_count_before = len(state.reasoning_history)
                with active_tool_call_context(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    node_id=self._source_node_id(),
                    state=state,
                    emitter=emitter,
                ):
                    result = await tool.run(tool_args, state)
                self._record_reason_tool_call(
                    tool=tool,
                    tool_args=tool_args,
                    state=state,
                    reasoning_count_before=reasoning_count_before,
                )
                state.tool_results[tool_name] = result

                tool_duration = (time.time() - tool_start) * 1000
                tracer.record_tool_result(tool_span, result, tool_duration)
                tracer.record_state_snapshot(tool_span, state)
                state_delta = build_state_delta(before_tool_state, state)
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    result_json={
                        "result": str(result),
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
                        "content": str(result),
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
                logger.error(f"Tool {tool_name} failed: {e}")
                completed = await runtime.record_activity_completed(
                    activity_id=activity_id,
                    error=str(e),
                )
                if not completed:
                    raise RuntimeError(f"Failed to mark tool activity as failed: {activity_id!r}")
                enabled, allow_types = self._exception_policy_from_node_config()
                if should_absorb_exception(e, enabled=enabled, allow_types=allow_types):
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
        variables: JsonObject = {
            **flow_variables,
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

    async def _emit_pending_ui_events(
        self,
        emitter: BaseEmitter,
        state: ExecutionState,
    ) -> None:
        await emit_pending_ui_events(emitter=emitter, state=state)
