"""
ReAct runner - реализация ReAct паттерна.

Zero-Guess: все методы работают с ExecutionState.
Stream-first: LLM ВСЕГДА вызывается как stream.
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any
from collections.abc import AsyncGenerator

from a2a.types import (
    Message,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import ReactLoopMode
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
from apps.flows.src.runtime.exception_policy import should_absorb_exception
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.llm_byok import is_llm_byok_override
from apps.flows.src.runtime.llm_override_params import (
    client_kwargs_from_override,
    split_llm_override_for_client,
)
from apps.flows.src.state.cancellation import (
    FlowCancelled,
    check_cancellation,
    get_cancellation_token,
)
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming import BaseEmitter, Emitter
from apps.flows.src.streaming.ui_events import emit_pending_ui_events
from apps.flows.src.tools.base import sanitize_tool_name
from apps.flows.src.variables import VariableResolver
from core.billing import get_cbr_usd_to_rub_rate
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm import (
    LLMClient,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
    MockLLM,
    StreamEvent,
    get_llm_for_state,
    should_use_platform_default_free_pool,
)
from core.config import get_settings
from core.context import get_context
from core.errors import ToolExecutionError
from core.logging import get_logger
from core.state import (
    ExecutionExceptionRecord,
    ExecutionState,
    InterruptPathItem,
    PromptHistoryItem,
)
from core.state.mutation_policy import FROZEN_STATE_FIELDS, USER_TOOL_PARALLEL_STATE_MERGE_FIELDS
from core.tracing import TraceContext, get_tracer
from core.tracing.context import get_current_trace_context

from .base_runner import BaseLlmNodeRunner

logger = get_logger(__name__)

def _get_trace_ctx_from_state() -> TraceContext | None:
    """Получает TraceContext из ContextVar worker'а."""
    trace_data = get_current_trace_context()
    if trace_data:
        return TraceContext.from_dict(trace_data)
    return None


def _get_message_metadata(msg) -> dict[str, Any]:
    """Получает metadata из Message."""
    if hasattr(msg, "metadata"):
        return msg.metadata or {}
    if isinstance(msg, dict):
        return msg.get("metadata") or {}
    return {}


class LlmNodeRunner(BaseLlmNodeRunner):
    """
    Runner для LLM-нод (ReAct цикл).
    Stream-first: ТОЛЬКО STREAM!
    """

    MAX_ITERATIONS = 10
    MAX_STREAM_IDLE_RETRIES = 4  # При idle timeout 10с — макс 50с ожидания (5 попыток × 10с)

    def __init__(
        self,
        node_config,
        tools: list[Any],
        llm,
        prompt: str,
        llm_node=None,
        *,
        container: FlowRuntimeContainer | None = None,
    ):
        super().__init__(
            node_config=node_config,
            tools=tools,
            llm=llm,
            prompt=prompt,
            llm_node=llm_node,
        )
        self.container = container

    def _resolve_tool_by_call_name(self, call_name: str):
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
            return self.llm_node._get_filtered_messages(state)
        return list(state.messages)

    async def run(
        self,
        input_data: dict[str, Any],
        state: ExecutionState,
        emitter: BaseEmitter | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Выполняет ReAct цикл.

        Args:
            input_data: Входные данные
            state: ExecutionState агента
            emitter: Emitter для публикации событий (BaseEmitter или его наследники)
        """
        task_id = state.task_id
        context_id = state.context_id

        if emitter is None:
            container = self.container
            if container is not None:
                emitter = Emitter(container.redis_client, state)
            else:
                from apps.flows.src.streaming.memory import InMemoryEmitter

                emitter = InMemoryEmitter(state)

        user_content = input_data.get("content", "")
        llm_node_label = self.node_config.name if self.node_config else "unknown"
        sid = self._source_node_id()

        interrupt_path = InterruptManager.get_interrupt_path(state)

        if interrupt_path:
            if user_content:
                await self._handle_resume(
                    state, user_content, interrupt_path, context_id, task_id
                )
            else:
                InterruptManager.clear_interrupt_path(state)
        elif user_content:
            state.messages.append(
                new_user_message(
                    user_content, sid, context_id=context_id, task_id=task_id
                )
            )

        async for event in self._react_loop(
            state, llm_node_label, context_id, task_id, emitter
        ):
            yield event

    def _messages_to_dict(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Конвертирует Message объекты в dict для трейсинга."""
        result = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                result.append(msg.model_dump())
            elif isinstance(msg, dict):
                result.append(msg)
            else:
                result.append({"role": "unknown", "content": str(msg)})
        return result

    def _get_react_config(self) -> tuple[ReactLoopMode, str, int, bool, str | None]:
        """Возвращает конфигурацию ReAct цикла."""
        if self.node_config and self.node_config.react:
            react = self.node_config.react
            return react.loop_mode, react.exit_tool, react.max_iterations, react.strict, react.reminder_message
        return ReactLoopMode.AUTO, "finish", self.MAX_ITERATIONS, True, None

    def _find_exit_tool_call(
        self, tool_calls: list[dict[str, Any]], exit_tool: str
    ) -> dict[str, Any] | None:
        """Ищет exit tool среди tool_calls."""
        for tc in tool_calls:
            if tc.get("name") == exit_tool:
                return tc
        return None

    def _find_tool_call_in_messages(
        self, messages: list[Message], tool_name: str
    ) -> dict[str, Any]:
        """Ищет tool_call по имени в последнем assistant сообщении."""
        for msg in reversed(messages):
            metadata = _get_message_metadata(msg)
            tool_calls = metadata.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    if tc.get("name") == tool_name:
                        return tc
                break
        return {}

    def _ensure_assistant_tool_calls(
        self,
        state: ExecutionState,
        tool_call_id: str,
        tool_call: dict[str, Any],
        context_id: str,
        task_id: str | None = None,
    ) -> None:
        """Гарантирует наличие assistant.tool_calls перед tool_result."""
        sid = self._source_node_id()
        for msg in reversed(state.messages):
            metadata = _get_message_metadata(msg)
            if metadata.get("tool_calls"):
                for tc in metadata["tool_calls"]:
                    if tc.get("id") == tool_call_id:
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
        call_type = next_call.type
        call_id = next_call.id
        tool_call = next_call.tool_call or {}

        if not tool_call:
            tool_call = self._find_tool_call_in_messages(state.messages, call_id)

        tool_call_id = tool_call.get("id", call_id)
        sid = self._source_node_id()

        logger.info(
            f"Resume: type={call_type}, id={call_id}, tool_call_id={tool_call_id}, "
            f"path_len={len(interrupt_path)}, answer={user_answer[:50]}..."
        )

        if call_type == NodeType.LLM_NODE.value:
            # NodeAsToolWrapper сам обрабатывает resume через interrupt_path
            # Передаем ответ пользователя в state.content
            state.content = user_answer

            try:
                tool_results = await self._execute_tools_parallel(
                    [{"name": call_id, "id": tool_call_id, "arguments": {"query": user_answer}}],
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
                    state, e.body, tool_call, getattr(e, "correlation_id", None)
                )
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
        model = (
            self.node_config.llm_override.model
            if self.node_config and self.node_config.llm_override and self.node_config.llm_override.model
            else "unknown"
        )

        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Контекст с active_company обязателен для LLM-ноды")
        if actx.user is None or not str(actx.user.user_id).strip():
            raise ValueError("Контекст с user обязателен для LLM-ноды (биллинг и уведомления)")
        container = self.container
        if container is None:
            raise RuntimeError("LlmNodeRunner requires FlowContainer for billing")
        override = self.node_config.llm_override if self.node_config else None
        allow_platform_paid_fallback = True
        byok_override = is_llm_byok_override(override)
        (
            billing_model,
            _billing_temp,
            billing_provider,
            billing_api_key,
            billing_base_url,
            _billing_max_tok,
            billing_folder_id,
            _billing_fallback_models,
        ) = split_llm_override_for_client(override)
        uses_platform_free_pool = should_use_platform_default_free_pool(
            model_name=billing_model,
            provider=billing_provider,
            api_key=billing_api_key,
            base_url=billing_base_url,
            folder_id=billing_folder_id,
            settings=get_settings(),
        )
        if not byok_override:
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
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": output_schema
                }
            }
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
                        tool_calls = None
                        llm_start = time.time()
                        input_tokens = 0
                        output_tokens = 0
                        provider_reported_cost: float | None = None
                        provider_upstream_inference_cost: float | None = None
                        settlement_quantity_rub: int | None = None

                        llm, stream_kw, max_tok = self._resolve_llm_client(
                            state,
                            allow_platform_paid_fallback=allow_platform_paid_fallback,
                        )
                        llm_provider = getattr(llm, "llm_provider", None)
                        byok = is_llm_byok_override(
                            self.node_config.llm_override if self.node_config else None
                        )
                        billing_res: str | None = "llm:byok" if byok else None

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
                                    stream_kw,
                                    max_tok,
                                    llm_messages,
                                    tools_schema,
                                    context_id,
                                    task_id,
                                    response_format,
                                    state,
                                ):
                                    should_yield = True

                                    if isinstance(event, TaskArtifactUpdateEvent):
                                        artifact_name = event.artifact.name or "response"
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
                                            md = event.status.message.metadata
                                            tc = md.get("tool_calls")
                                            if tc:
                                                tool_calls = tc
                                            usage = md.get("usage")
                                            if usage:
                                                input_tokens = usage.get("input_tokens", 0)
                                                output_tokens = usage.get("output_tokens", 0)
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
                                llm_provider == "openrouter"
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
                            tracer.record_llm_response(
                                llm_span,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                has_tool_calls=bool(tool_calls),
                                duration_ms=llm_duration,
                                response_content=content,
                                tool_calls=tool_calls,
                                llm_provider=llm_provider,
                                provider_reported_cost=provider_reported_cost,
                                provider_upstream_inference_cost=provider_upstream_inference_cost,
                                settlement_quantity_rub=settlement_quantity_rub,
                                billing_resource_name=billing_res,
                            )

                        if tool_calls:
                            tool_names = [tc.get("name", "?") for tc in tool_calls]
                            logger.info(f"[llm_node:{llm_node_label}] Вызов tools: {tool_names}")

                            exit_call = self._find_exit_tool_call(tool_calls, exit_tool_name)

                            if exit_call and loop_mode == ReactLoopMode.EXPLICIT:
                                exit_args = exit_call.get("arguments", {})
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

                                exit_call_id = exit_call.get("id", exit_tool_name)
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
                                tool_call_id = tc.get("id", tc.get("name", "unknown"))
                                tool_name = tc.get("name", "unknown")
                                tool_args = tc.get("arguments", {})

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
                                    tool_calls, state, trace_ctx
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
                                            tc.get("name", "unknown")
                                            for tc in tool_calls
                                            if tc.get("id") == tool_call_id
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

                            except FlowInterrupt as e:
                                interrupted_tc = tool_calls[0]
                                logger.info(
                                    f"[llm_node:{llm_node_label}] Interrupt: tool={interrupted_tc['name']}"
                                )

                                async with tracer.interrupt_span(
                                    e.question, interrupted_tc["name"], trace_ctx=trace_ctx
                                ):
                                    # Добавляем элемент в путь только если это первичный interrupt
                                    # (не от вложенного субагента)
                                    if not state.interrupt_path:
                                        InterruptManager.push_interrupt_path(
                                            state,
                                            InterruptPathItem(
                                                type="tool",
                                                id=interrupted_tc["name"],
                                                tool_call=interrupted_tc,
                                            ),
                                        )

                                    InterruptManager.apply_interrupt(
                                        state,
                                        e.body,
                                        interrupted_tc,
                                        getattr(e, "correlation_id", None),
                                    )
                                raise
                        else:
                            # Structured Output - всегда завершаем после первого ответа
                            if structured_output and output_schema:
                                try:
                                    parsed_output = json.loads(content)
                                    setattr(state, "structured_output_result", parsed_output)
                                    final_response = content
                                    logger.info(
                                        f"[llm_node:{llm_node_label}] Structured Output получен: {list(parsed_output.keys()) if isinstance(parsed_output, dict) else type(parsed_output)}"
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
                                    break

                                logger.warning(
                                    f"[llm_node:{llm_node_label}] EXPLICIT strict: LLM вернул текст без "
                                    f"exit_tool '{exit_tool_name}', добавляем reminder"
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
            except FlowInterrupt:
                tracer.record_state_snapshot(llm_node_span, state)
                raise
            finally:
                if final_response:
                    state.response = final_response
                    tracer.record_state_snapshot(llm_node_span, state)

    def _resolve_llm_client(
        self,
        state: ExecutionState,
        *,
        allow_platform_paid_fallback: bool = True,
    ) -> tuple[LLMClient | MockLLM, dict[str, Any], int | None]:
        override = self.node_config.llm_override if self.node_config else None
        max_tok = override.max_tokens if override is not None else None
        client_kwargs = client_kwargs_from_override(override, state)
        llm = get_llm_for_state(
            state,
            **client_kwargs,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
        )
        return llm, {}, max_tok

    async def _call_llm(
        self,
        llm: LLMClient | MockLLM,
        stream_kw: dict[str, Any],
        max_tok: int | None,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        context_id: str,
        task_id: str,
        response_format: dict[str, Any] | None,
        state: ExecutionState,
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


        for attempt in range(1, self.MAX_STREAM_IDLE_RETRIES + 2):  # +2: 1 original + N retries
            try:
                async for event in llm.stream(
                    messages,
                    tools,
                    response_format,
                    task_id,
                    context_id,
                    max_tokens=max_tok,
                    stream_cancel_poll=_stream_cancel_poll,
                    **stream_kw,
                ):
                    await check_cancellation(state)
                    yield event
                return  # Стрим завершился нормально
            except LLMStreamUserCancelledError:
                tok = get_cancellation_token()
                raise FlowCancelled(tok.task_id if tok is not None else task_id)
            except LLMStreamIdleTimeoutError as e:
                if attempt <= self.MAX_STREAM_IDLE_RETRIES:
                    logger.warning(
                        "LLM stream idle timeout (attempt %d/%d), retrying: "
                        "idle=%.1fs, chunks=%d",
                        attempt,
                        self.MAX_STREAM_IDLE_RETRIES + 1,
                        e.idle_seconds,
                        e.chunks_received,
                    )
                    continue
                # Все retry исчерпаны
                logger.error(
                    "LLM stream idle timeout after %d attempts, giving up: "
                    "idle=%.1fs, chunks=%d",
                    attempt, e.idle_seconds, e.chunks_received,
                )
                raise

    async def _execute_tools_parallel(
        self,
        tool_calls: list[dict[str, Any]],
        state: ExecutionState,
        trace_ctx: TraceContext | None = None,
    ) -> list[dict[str, str]]:
        """
        Выполняет tools ПАРАЛЛЕЛЬНО через asyncio.gather.

        Каждый tool получает копию state.
        Результаты мержатся: messages extend, остальное - кто последний.
        """
        if len(tool_calls) == 1:
            # Один tool - выполняем напрямую без копирования
            return await self._execute_single_tool(tool_calls[0], state, trace_ctx)

        # Несколько tools - параллельное выполнение
        original_msg_count = len(state.messages)

        # Создаем копии state для каждого tool
        state_copies = [
            ExecutionState.model_validate(state.model_dump(exclude_none=False))
            for _ in tool_calls
        ]

        # Запускаем все tools параллельно
        tasks = [
            self._execute_single_tool(tc, state_copy, trace_ctx)
            for tc, state_copy in zip(tool_calls, state_copies)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Собираем результаты и мержим state
        tool_results = []
        for i, (tc, result, state_copy) in enumerate(zip(tool_calls, results, state_copies)):
            tool_name = tc["name"]
            tool_call_id = tc.get("id", tool_name)

            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                if isinstance(result, FlowInterrupt):
                    raise result
                if isinstance(result, ToolExecutionError):
                    raise result
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
                raise ToolExecutionError(tool_name, result)

            # Мержим state: messages extend, остальное перезаписываем
            new_messages = state_copy.messages[original_msg_count:]
            state.messages.extend(new_messages)

            # tool_results - мержим (не перезаписываем!)
            state.tool_results.update(state_copy.tool_results)

            for field in USER_TOOL_PARALLEL_STATE_MERGE_FIELDS:
                value = getattr(state_copy, field, None)
                if value is not None:
                    if field == "variables" and isinstance(value, dict):
                        merged_vars = dict(state.variables)
                        merged_vars.update(value)
                        state.variables = merged_vars
                    else:
                        setattr(state, field, value)

            extra_src = getattr(state_copy, "__pydantic_extra__", None) or {}
            for ek, ev in extra_src.items():
                if ek in FROZEN_STATE_FIELDS:
                    continue
                if ev is not None:
                    setattr(state, ek, ev)

            tool_results.extend(result)

        return tool_results

    async def _execute_single_tool(
        self,
        tc: dict[str, Any],
        state: ExecutionState,
        trace_ctx: TraceContext | None = None,
    ) -> list[dict[str, str]]:
        """Выполняет один tool."""
        tracer = get_tracer()
        tool_name = tc["name"]
        tool_args = tc.get("arguments", {})
        tool_call_id = tc.get("id", tool_name)

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

        nested_flow_tool = hasattr(tool, "flow_id")

        async with tracer.tool_call_span(
            tool_name, tool_call_id, tool_args, nested_flow_tool, trace_ctx=trace_ctx
        ) as tool_span:
            tool_start = time.time()

            logger.info(f"Выполняю tool: {tool_name}")
            try:
                result = await tool.run(tool_args, state)
                state.tool_results[tool_name] = result

                tool_duration = (time.time() - tool_start) * 1000
                tracer.record_tool_result(tool_span, result, tool_duration)
                tracer.record_state_snapshot(tool_span, state)

                return [
                    {
                        "tool_call_id": tool_call_id,
                        "content": str(result),
                    }
                ]
            except FlowInterrupt:
                raise
            except Exception as e:
                tool_duration = (time.time() - tool_start) * 1000
                tracer.record_tool_result(tool_span, None, tool_duration, error=str(e))
                logger.error(f"Tool {tool_name} failed: {e}")
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

    async def _render_prompt(self, state: ExecutionState) -> str:
        """Рендерит промпт с переменными и сохраняет в историю."""
        prompt_template = self.prompt
        flow_variables = self.get_variables(state)
        variables = {**flow_variables, **(self.node_config.local_variables if self.node_config else {})}

        if self.llm_node:
            prompt_template, variables = await self.llm_node.before_prompt_render(
                prompt_template, state, variables
            )

        resolved_vars = VariableResolver.resolve_all(local_vars=variables)

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

            tracer.record_prompt_result(span, rendered_prompt, resolved_vars)
            self._save_prompt_to_history(state, prompt_template, rendered_prompt, resolved_vars, node_id)

        return rendered_prompt

    def _save_prompt_to_history(
        self,
        state: ExecutionState,
        template: str,
        rendered: str,
        variables: dict[str, Any],
        node_id: str,
    ) -> None:
        """Сохраняет промпт в историю если он изменился."""
        prompt_hash = hashlib.md5(rendered.encode()).hexdigest()

        if state.prompt_history:
            last = state.prompt_history[-1]
            if last.prompt_hash == prompt_hash:
                return

        safe_vars = {
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

    def _build_tools_schema(self) -> list[dict[str, Any]]:
        """Строит схему инструментов для LLM."""
        schema = []
        for tool in self.tools:
            if hasattr(tool, "to_openai_schema"):
                schema.append(tool.to_openai_schema())
            elif hasattr(tool, "name") and hasattr(tool, "description"):
                schema.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": getattr(tool, "parameters", {}),
                        },
                    }
                )
        return schema

    async def _emit_pending_ui_events(
        self,
        emitter: BaseEmitter,
        state: ExecutionState,
    ) -> None:
        await emit_pending_ui_events(emitter=emitter, state=state)
