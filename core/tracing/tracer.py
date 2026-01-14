"""
PlatformTracer - основной класс для создания spans.

OpenTelemetry spans используются для трейсинга выполнения агентов.
Ошибки "Failed to detach context" при закрытии async generators безопасны и подавляются.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from core.logging import get_logger

from . import attributes as attr

if TYPE_CHECKING:
    from core.state import ExecutionState
from .context import TraceContext
from .provider import is_tracing_enabled

if TYPE_CHECKING:
    from .repository import SpanRepository

logger = get_logger(__name__)

# При закрытии async generators (GeneratorExit) OpenTelemetry пытается detach
# контекст который был создан в другом async контексте. Это безопасно игнорировать.
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
logging.getLogger("opentelemetry.trace").addFilter(
    lambda record: "Failed to detach context" not in record.getMessage()
)
logging.getLogger("opentelemetry.sdk.trace").addFilter(
    lambda record: "Failed to detach context" not in record.getMessage()
)

_tracer: Optional["PlatformTracer"] = None
_span_repository: Optional["SpanRepository"] = None


def set_span_repository(repository: "SpanRepository") -> None:
    """Устанавливает репозиторий для сохранения spans в PostgreSQL."""
    global _span_repository
    _span_repository = repository


def get_tracer() -> "PlatformTracer":
    """Получает глобальный PlatformTracer."""
    global _tracer
    if _tracer is None:
        _tracer = PlatformTracer()
    return _tracer


class PlatformTracer:
    """
    Централизованный трейсер для платформы Platform.
    
    Создает spans с правильными атрибутами и сохраняет в PostgreSQL.
    """

    def __init__(self, service_name: str = "platform"):
        self._otel_tracer = trace.get_tracer(service_name)
        self._service_name = service_name

    def _generate_ids(self) -> tuple[str, str]:
        """Генерирует trace_id и span_id."""
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        return trace_id, span_id

    async def _save_span(
        self,
        span: Span,
        operation_name: str,
        kind: str,
        start_time: datetime,
        trace_ctx: Optional[TraceContext],
        extra_attrs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Сохраняет span в PostgreSQL."""
        if _span_repository is None:
            logger.warning(f"SpanRepository not set, span '{operation_name}' not saved")
            return

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        
        parent_ctx = span.parent
        parent_span_id = format(parent_ctx.span_id, "016x") if parent_ctx else None

        status = "OK"
        status_message = None
        if span.status.status_code == StatusCode.ERROR:
            status = "ERROR"
            status_message = span.status.description

        # Собираем все атрибуты
        all_attrs = dict(span.attributes) if span.attributes else {}
        if extra_attrs:
            all_attrs.update(extra_attrs)

        span_data = {
            "span_id": span_id,
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "operation_name": operation_name,
            "kind": kind,
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": duration_ms,
            "status": status,
            "status_message": status_message,
            "user_id": trace_ctx.user_id if trace_ctx else None,
            "user_name": trace_ctx.user_name if trace_ctx else None,
            "user_groups": trace_ctx.user_groups if trace_ctx else None,
            "session_auth": trace_ctx.session_auth if trace_ctx else None,
            "session_agent": trace_ctx.session_agent if trace_ctx else None,
            "agent_id": trace_ctx.agent_id if trace_ctx else all_attrs.get(attr.ATTR_FLOW_ID),
            "task_id": trace_ctx.task_id if trace_ctx else all_attrs.get(attr.ATTR_TASK_ID),
            "context_id": trace_ctx.context_id if trace_ctx else all_attrs.get(attr.ATTR_CONTEXT_ID),
            "skill_id": trace_ctx.skill_id if trace_ctx else all_attrs.get(attr.ATTR_SKILL_ID),
            "channel": trace_ctx.channel if trace_ctx else all_attrs.get(attr.ATTR_CHANNEL),
            "node_id": all_attrs.get(attr.ATTR_NODE_ID),
            "agent_name": all_attrs.get(attr.ATTR_AGENT_NAME),
            "is_resume": trace_ctx.is_resume if trace_ctx else all_attrs.get(attr.ATTR_IS_RESUME),
            "attributes": all_attrs,
            "events": None,
        }

        await _span_repository.save_span(span_data)

    def create_trace_context(
        self,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_groups: Optional[List[str]] = None,
        session_auth: Optional[str] = None,
        session_agent: Optional[str] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        channel: Optional[str] = None,
        is_resume: bool = False,
    ) -> TraceContext:
        """Создает новый TraceContext."""
        trace_id, span_id = self._generate_ids()
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            user_name=user_name,
            user_groups=user_groups or [],
            session_auth=session_auth,
            session_agent=session_agent,
            task_id=task_id,
            context_id=context_id,
            agent_id=agent_id,
            skill_id=skill_id,
            channel=channel,
            is_resume=is_resume,
        )

    def _base_attributes(self, trace_ctx: Optional[TraceContext]) -> Dict[str, Any]:
        """Возвращает базовые атрибуты для всех spans."""
        if trace_ctx is None:
            return {}
        
        attrs = {}
        if trace_ctx.user_id:
            attrs[attr.ATTR_USER_ID] = trace_ctx.user_id
        if trace_ctx.user_name:
            attrs[attr.ATTR_USER_NAME] = trace_ctx.user_name
        if trace_ctx.user_groups:
            attrs[attr.ATTR_USER_GROUPS] = ",".join(trace_ctx.user_groups)
        if trace_ctx.session_auth:
            attrs[attr.ATTR_SESSION_AUTH] = trace_ctx.session_auth
        if trace_ctx.session_agent:
            attrs[attr.ATTR_SESSION_AGENT] = trace_ctx.session_agent
        if trace_ctx.task_id:
            attrs[attr.ATTR_TASK_ID] = trace_ctx.task_id
        if trace_ctx.context_id:
            attrs[attr.ATTR_CONTEXT_ID] = trace_ctx.context_id
        if trace_ctx.agent_id:
            attrs[attr.ATTR_FLOW_ID] = trace_ctx.agent_id
        if trace_ctx.skill_id:
            attrs[attr.ATTR_SKILL_ID] = trace_ctx.skill_id
        if trace_ctx.channel:
            attrs[attr.ATTR_CHANNEL] = trace_ctx.channel
        if trace_ctx.is_resume:
            attrs[attr.ATTR_IS_RESUME] = trace_ctx.is_resume
        
        return attrs

    @asynccontextmanager
    async def request_span(
        self,
        method: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для HTTP запроса (message/send, message/stream)."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes["http.method"] = method

        with self._otel_tracer.start_as_current_span(
            name=f"request.{method}",
            kind=SpanKind.SERVER,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"request.{method}", "SERVER", start_time, trace_ctx)

    @asynccontextmanager
    async def flow_span(
        self,
        agent_id: str,
        entry_node: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения flow."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_FLOW_ID] = agent_id
        attributes[attr.ATTR_FLOW_ENTRY] = entry_node

        with self._otel_tracer.start_as_current_span(
            name=f"flow.{agent_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"flow.{agent_id}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def node_span(
        self,
        node_id: str,
        node_type: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения ноды."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_NODE_ID] = node_id
        attributes[attr.ATTR_NODE_TYPE] = node_type

        with self._otel_tracer.start_as_current_span(
            name=f"node.{node_type}.{node_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"node.{node_type}.{node_id}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def agent_span(
        self,
        agent_name: str,
        agent_id: Optional[str] = None,
        model: Optional[str] = None,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения агента."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_AGENT_NAME] = agent_name
        attributes[attr.ATTR_AGENT_ID] = agent_id or agent_name
        if model:
            attributes[attr.ATTR_LLM_MODEL] = model

        with self._otel_tracer.start_as_current_span(
            name=f"agent.{agent_name}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"agent.{agent_name}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def react_iteration_span(
        self,
        iteration: int,
        agent_name: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для одной итерации ReAct цикла."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_REACT_ITERATION] = iteration
        attributes[attr.ATTR_AGENT_NAME] = agent_name

        with self._otel_tracer.start_as_current_span(
            name=f"react.iteration.{iteration}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"react.iteration.{iteration}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def llm_call_span(
        self,
        model: str,
        messages_count: int,
        tools_count: int,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для вызова LLM."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_LLM_MODEL] = model
        attributes["llm.messages_count"] = messages_count
        attributes["llm.tools_count"] = tools_count
        attributes[attr.ATTR_LLM_STREAM] = True

        with self._otel_tracer.start_as_current_span(
            name=f"llm.{model}",
            kind=SpanKind.CLIENT,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"llm.{model}", "CLIENT", start_time, trace_ctx)

    def record_llm_response(
        self,
        span: Span,
        input_tokens: int,
        output_tokens: int,
        has_tool_calls: bool,
        duration_ms: float,
    ) -> None:
        """Записывает результат LLM вызова в span."""
        span.set_attributes(
            {
                attr.ATTR_LLM_INPUT_TOKENS: input_tokens,
                attr.ATTR_LLM_OUTPUT_TOKENS: output_tokens,
                attr.ATTR_LLM_TOTAL_TOKENS: input_tokens + output_tokens,
                attr.ATTR_LLM_HAS_TOOL_CALLS: has_tool_calls,
                attr.ATTR_LLM_DURATION_MS: duration_ms,
            }
        )

    @asynccontextmanager
    async def tool_call_span(
        self,
        tool_name: str,
        tool_call_id: str,
        args: Dict[str, Any],
        is_agent_tool: bool = False,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для вызова tool."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_TOOL_NAME] = tool_name
        attributes[attr.ATTR_TOOL_CALL_ID] = tool_call_id
        attributes[attr.ATTR_TOOL_IS_AGENT] = is_agent_tool
        # Обрезаем args для безопасности
        args_str = str(args)[:500]
        attributes[attr.ATTR_TOOL_ARGS] = args_str

        with self._otel_tracer.start_as_current_span(
            name=f"tool.{tool_name}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"tool.{tool_name}", "INTERNAL", start_time, trace_ctx)

    def record_tool_result(
        self,
        span: Span,
        result: Any,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Записывает результат tool в span."""
        result_str = str(result)[:500]
        span.set_attributes(
            {
                attr.ATTR_TOOL_RESULT: result_str,
                attr.ATTR_TOOL_DURATION_MS: duration_ms,
            }
        )
        if error:
            span.set_status(Status(StatusCode.ERROR, error))
            span.set_attribute(attr.ATTR_TOOL_ERROR, error)

    def record_state_snapshot(self, span: Span, state: "ExecutionState") -> None:
        """Записывает snapshot state в span."""
        # Конвертируем ExecutionState в dict для JSON сериализации
        state_dict = state.model_dump(exclude_none=False)
        
        snapshot = {
            k: v
            for k, v in state_dict.items()
            if not k.startswith("__") or k == "__tools__"
        }
        snapshot_str = json.dumps(snapshot, ensure_ascii=False, default=str)[:4000]
        span.set_attribute(attr.ATTR_STATE_SNAPSHOT, snapshot_str)
        logger.debug(f"Recorded state snapshot: {len(snapshot)} fields, {len(snapshot_str)} chars")

    @asynccontextmanager
    async def interrupt_span(
        self,
        question: str,
        tool_name: str,
        path_depth: int = 0,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для interrupt (ask_user)."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_INTERRUPT_QUESTION] = question[:200]
        attributes[attr.ATTR_INTERRUPT_TOOL] = tool_name
        attributes[attr.ATTR_INTERRUPT_PATH_DEPTH] = path_depth

        with self._otel_tracer.start_as_current_span(
            name="interrupt.ask_user",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, "interrupt.ask_user", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def prompt_build_span(
        self,
        node_id: str,
        template: str,
        variables: Dict[str, Any],
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для сборки системного промпта."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        import hashlib
        
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_PROMPT_NODE_ID] = node_id
        attributes[attr.ATTR_PROMPT_TEMPLATE_LENGTH] = len(template)
        attributes[attr.ATTR_PROMPT_VARIABLES_COUNT] = len(variables)
        
        # Фильтруем переменные - оставляем только скалярные значения
        safe_vars = {
            k: v for k, v in variables.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        variables_str = json.dumps(safe_vars, ensure_ascii=False, default=str)[:2000]
        attributes[attr.ATTR_PROMPT_VARIABLES] = variables_str

        with self._otel_tracer.start_as_current_span(
            name=f"prompt.build.{node_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"prompt.build.{node_id}", "INTERNAL", start_time, trace_ctx)

    def record_prompt_result(
        self,
        span: Span,
        rendered_prompt: str,
        variables: Dict[str, Any],
    ) -> None:
        """Записывает результат сборки промпта в span."""
        import hashlib
        
        prompt_hash = hashlib.md5(rendered_prompt.encode()).hexdigest()
        span.set_attributes(
            {
                attr.ATTR_PROMPT_RENDERED_LENGTH: len(rendered_prompt),
                attr.ATTR_PROMPT_HASH: prompt_hash,
            }
        )

    def get_current_trace_context(self) -> Optional[TraceContext]:
        """Получает текущий trace context для propagation."""
        span = trace.get_current_span()
        if not span or not span.is_recording():
            return None

        ctx = span.get_span_context()
        return TraceContext(
            trace_id=format(ctx.trace_id, "032x"),
            span_id=format(ctx.span_id, "016x"),
        )

    def set_error(self, span: Span, error: Exception) -> None:
        """Помечает span как ошибку."""
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.set_attribute(attr.ATTR_ERROR_MESSAGE, str(error))
        span.set_attribute(attr.ATTR_ERROR_TYPE, type(error).__name__)
        span.record_exception(error)

