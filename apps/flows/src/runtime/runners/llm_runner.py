"""
ReAct runner - реализация ReAct паттерна.

Zero-Guess: все методы работают с ExecutionState.
Stream-first: LLM ВСЕГДА вызывается как stream.
"""

import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)

from apps.flows.src.runtime.exceptions import FlowInterrupt, ToolExecutionError
from core.clients.llm import StreamEvent, get_llm_for_state
from apps.flows.src.container import get_container
from core.logging import get_logger
from apps.flows.src.models import ReactLoopMode
from apps.flows.src.models.enums import NodeType
from apps.flows.src.state.interrupt_manager import InterruptManager
from core.state import ExecutionState, InterruptPathItem, PromptHistoryItem
from apps.flows.src.streaming import Emitter, BaseEmitter
from core.tracing import TraceContext, get_tracer
from core.tracing.context import get_current_trace_context
from apps.flows.src.variables import VariableResolver
from core.errors import ToolExecutionError

from .base_runner import BaseLlmNodeRunner
from apps.flows.src.tools.base import BaseTool, ToolType

logger = get_logger(__name__)


def _get_trace_ctx_from_state() -> Optional[TraceContext]:
    """Получает TraceContext из ContextVar worker'а."""
    trace_data = get_current_trace_context()
    if trace_data:
        return TraceContext.from_dict(trace_data)
    return None


def new_user_message(
    content: str,
    source_node_id: str,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """Создаёт сообщение от пользователя."""
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata={"node_id": source_node_id},
    )


def new_assistant_message(
    content: str,
    source_node_id: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """Создаёт сообщение от ассистента."""
    meta: Dict[str, Any] = {"node_id": source_node_id}
    if tool_calls:
        meta["tool_calls"] = tool_calls
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata=meta,
    )


def new_tool_result_message(
    tool_call_id: str,
    content: str,
    source_node_id: str,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """Создаёт сообщение с результатом tool."""
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata={"tool_call_id": tool_call_id, "node_id": source_node_id},
    )


def new_system_message(
    content: str,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
    source_node_id: Optional[str] = None,
) -> Message:
    """Создаёт системное сообщение (для LLM-запроса или для записи в state.messages)."""
    meta: Dict[str, Any] = {"system": True}
    if source_node_id is not None:
        meta["node_id"] = source_node_id
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.agent,
        parts=[Part(root=TextPart(text=content))],
        context_id=context_id,
        task_id=task_id,
        metadata=meta,
    )


def _get_message_metadata(msg) -> Dict[str, Any]:
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

    def _source_node_id(self) -> str:
        if not self.node_config:
            raise ValueError("LlmNodeRunner.node_config required for message tagging")
        return self.node_config.node_id

    def _messages_for_llm_context(self, state: ExecutionState) -> List[Message]:
        if self.llm_node is not None:
            return self.llm_node._get_filtered_messages(state)
        return list(state.messages)

    async def run(
        self,
        input_data: Dict[str, Any],
        state: ExecutionState,
        emitter: Optional[BaseEmitter] = None,
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
            container = get_container()
            emitter = Emitter(container.redis_client, state)

        user_content = input_data.get("content", "")
        llm_node_label = self.node_config.name if self.node_config else "unknown"
        sid = self._source_node_id()

        interrupt_path = InterruptManager.get_interrupt_path(state)

        if interrupt_path:
            if user_content:
                resumed = await self._handle_resume(
                    state, user_content, interrupt_path, context_id, task_id
                )
                if not resumed:
                    return
            else:
                InterruptManager.clear_interrupt_path(state)
        elif user_content:
            state.messages.append(new_user_message(user_content, sid, context_id, task_id))

        async for event in self._react_loop(
            state, llm_node_label, context_id, task_id, emitter
        ):
            yield event

    def _messages_to_dict(self, messages: List[Message]) -> List[Dict[str, Any]]:
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

    def _get_reason_tool_name(self) -> Optional[str]:
        """Находит имя reasoning tool по tool_type."""
        for tool in self.tools:
            if getattr(tool, "tool_type", None) == ToolType.REASON:
                return tool.name
        return None

    def _get_exit_tool_name(self) -> Optional[str]:
        """Находит имя exit tool по tool_type."""
        for tool in self.tools:
            if getattr(tool, "tool_type", None) == ToolType.EXIT:
                return tool.name
        return None

    def _find_tool_by_type(self, tool_type: ToolType) -> Optional[BaseTool]:
        """Находит tool по tool_type."""
        for tool in self.tools:
            if getattr(tool, "tool_type", None) == tool_type:
                return tool
        return None

    def _find_exit_tool_call(
        self, tool_calls: List[Dict[str, Any]], exit_tool: str
    ) -> Optional[Dict[str, Any]]:
        """Ищет exit tool среди tool_calls."""
        for tc in tool_calls:
            if tc.get("name") == exit_tool:
                return tc
        return None

    def _find_tool_call_in_messages(
        self, messages: List[Message], tool_name: str
    ) -> Dict[str, Any]:
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
        tool_call: Dict[str, Any],
        context_id: str,
        task_id: Optional[str] = None,
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
            new_assistant_message("", sid, [tool_call], context_id, task_id)
        )

    async def _handle_resume(
        self,
        state: ExecutionState,
        user_answer: str,
        interrupt_path: List[InterruptPathItem],
        context_id: str,
        task_id: Optional[str] = None,
    ) -> bool:
        """Обрабатывает resume после interrupt."""
        if not interrupt_path:
            return True

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
                            tr["tool_call_id"], tr["content"], sid, context_id, task_id
                        )
                    )
                InterruptManager.clear_interrupt_path(state)
            except FlowInterrupt as e:
                InterruptManager.set_interrupt(state, e.question, tool_call)
                raise
        else:
            self._ensure_assistant_tool_calls(
                state, tool_call_id, tool_call, context_id, task_id
            )
            state.messages.append(
                new_tool_result_message(tool_call_id, user_answer, sid, context_id, task_id)
            )

        InterruptManager.clear_interrupt_path(state)
        return True

    async def _react_loop(
        self,
        state: ExecutionState,
        llm_node_label: str,
        context_id: str,
        task_id: str,
        emitter: Emitter,
    ) -> AsyncGenerator[StreamEvent, None]:
        """ReAct цикл со стримингом событий."""
        sid = self._source_node_id()
        system_prompt = await self._render_prompt(state)
        trace_ctx = _get_trace_ctx_from_state()
        tracer = get_tracer()
        model = self.node_config.llm_override.model if self.node_config and self.node_config.llm_override else "unknown"

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
            logger.info(f"[llm_node:{llm_node_label}] Structured Output режим, schema keys: {list(output_schema.get('properties', {}).keys())}")
        else:
            tools_schema = self._build_tools_schema()
            response_format = None

        loop_mode, exit_tool, max_iterations, strict, reminder_message = self._get_react_config()
        reason_tool_name = self._get_reason_tool_name()
        exit_tool_name = self._get_exit_tool_name() or exit_tool

        system_msg = new_system_message(system_prompt, context_id, task_id)

        iteration = 0
        final_response = ""

        async with tracer.llm_node_span(llm_node_label, model=model, trace_ctx=trace_ctx) as llm_node_span:
            try:
                while iteration < max_iterations:
                    iteration += 1
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

                        async with tracer.llm_call_span(
                            model, len(llm_messages), len(tools_schema) if tools_schema else 0, trace_ctx=trace_ctx
                        ) as llm_span:
                            llm_messages_for_trace = self._messages_to_dict(llm_messages)
                            tracer.record_llm_request(llm_span, llm_messages_for_trace, tools_schema, response_format)
                            
                            async for event in self._call_llm(
                                llm_messages, tools_schema, context_id, task_id, state, response_format
                            ):
                                should_yield = True
                                
                                if isinstance(event, TaskArtifactUpdateEvent):
                                    artifact_name = event.artifact.name or "response"
                                    if artifact_name != "reasoning":
                                        for part in event.artifact.parts:
                                            if hasattr(part.root, "text"):
                                                content += part.root.text
                                        if loop_mode == ReactLoopMode.EXPLICIT:
                                            should_yield = False
                                
                                if should_yield:
                                    await emitter.emit(event)
                                    yield event

                                if isinstance(event, TaskStatusUpdateEvent):
                                    if event.status.message and event.status.message.metadata:
                                        tool_calls = event.status.message.metadata.get("tool_calls")
                                        usage = event.status.message.metadata.get("usage")
                                        if usage:
                                            input_tokens = usage.get("input_tokens", 0)
                                            output_tokens = usage.get("output_tokens", 0)

                            llm_duration = (time.time() - llm_start) * 1000
                            tracer.record_llm_response(
                                llm_span,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                has_tool_calls=bool(tool_calls),
                                duration_ms=llm_duration,
                                response_content=content,
                                tool_calls=tool_calls,
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
                                    new_assistant_message(content, sid, tool_calls, context_id, task_id)
                                )
                                
                                exit_call_id = exit_call.get("id", exit_tool_name)
                                await emitter.emit_tool_call(exit_tool_name, exit_args, exit_call_id)
                                
                                state.messages.append(
                                    new_tool_result_message(
                                        exit_call_id, final_response, sid, context_id, task_id
                                    )
                                )
                                await emitter.emit_tool_result(exit_tool_name, final_response, exit_call_id)
                                
                                state.response = final_response
                                InterruptManager.clear_interrupt_path(state)
                                break

                            state.messages.append(
                                new_assistant_message(content, sid, tool_calls, context_id, task_id)
                            )

                            for tc in tool_calls:
                                tool_call_id = tc.get("id", tc.get("name", "unknown"))
                                tool_name = tc.get("name", "unknown")
                                tool_args = tc.get("arguments", {})
                                
                                tool_obj = next((t for t in self.tools if t.name == tool_name), None)
                                tool_type = tool_obj.tool_type.value if tool_obj else "tool"
                                
                                await emitter.emit_tool_call(tool_name, tool_args, tool_call_id, tool_type)

                            try:
                                tool_results = await self._execute_tools_parallel(
                                    tool_calls, state, trace_ctx
                                )

                                for tr in tool_results:
                                    state.messages.append(
                                        new_tool_result_message(
                                            tr["tool_call_id"], tr["content"], sid, context_id, task_id
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

                                pending_reasoning = getattr(state, "_pending_reasoning", None)
                                if pending_reasoning:
                                    await emitter.emit_reasoning(pending_reasoning)
                                    delattr(state, "_pending_reasoning")

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
                                    
                                    InterruptManager.set_interrupt(
                                        state, e.question, interrupted_tc
                                    )
                                raise
                        else:
                            # Structured Output - всегда завершаем после первого ответа
                            if structured_output and output_schema:
                                try:
                                    import json
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
                                        context_id,
                                        task_id,
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

    async def _call_llm(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]],
        context_id: str,
        task_id: str,
        state: ExecutionState,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Вызывает LLM - ТОЛЬКО STREAM."""
        model = self.node_config.llm_override.model if self.node_config and self.node_config.llm_override else None
        temp = self.node_config.llm_override.temperature if self.node_config and self.node_config.llm_override else None
        llm = get_llm_for_state(state, model_name=model, temperature=temp)

        async for event in llm.stream(messages, tools, response_format, task_id, context_id):
            yield event

    async def _execute_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        state: ExecutionState,
        trace_ctx: Optional[TraceContext] = None,
    ) -> List[Dict[str, str]]:
        """
        Выполняет tools ПАРАЛЛЕЛЬНО через asyncio.gather.
        
        Каждый tool получает копию state.
        Результаты мержатся: messages extend, остальное - кто последний.
        """
        import asyncio
        
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
            
            if isinstance(result, Exception):
                if isinstance(result, FlowInterrupt):
                    raise result
                logger.error(f"Tool {tool_name} failed: {result}")
                raise ToolExecutionError(f"Tool {tool_name} failed: {result}", error=result)
            
            # Мержим state: messages extend, остальное перезаписываем
            new_messages = state_copy.messages[original_msg_count:]
            state.messages.extend(new_messages)
            
            # tool_results - мержим (не перезаписываем!)
            state.tool_results.update(state_copy.tool_results)
            
            # Все поля (включая динамические) - перезаписываем
            state_dict = state_copy.model_dump(exclude_none=False)
            for field, value in state_dict.items():
                if field in ("messages", "tool_results"):
                    continue  # Уже обработали
                if value is not None:
                    setattr(state, field, value)
            
            tool_results.extend(result)
        
        return tool_results

    async def _execute_single_tool(
        self,
        tc: Dict[str, Any],
        state: ExecutionState,
        trace_ctx: Optional[TraceContext] = None,
    ) -> List[Dict[str, str]]:
        """Выполняет один tool."""
        tracer = get_tracer()
        tool_name = tc["name"]
        tool_args = tc.get("arguments", {})
        tool_call_id = tc.get("id", tool_name)
        
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            raise ToolExecutionError(
                f"Tool '{tool_name}' not found. Flow must be fully inline with all tools loaded.",
                error=None
            )
        
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
                raise ToolExecutionError(f"Tool {tool_name} failed: {e}", error=e)

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
        variables: Dict[str, Any],
        node_id: str,
    ) -> None:
        """Сохраняет промпт в историю если он изменился."""
        import hashlib
        from datetime import datetime, timezone
        
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

    def _build_tools_schema(self) -> List[Dict[str, Any]]:
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
