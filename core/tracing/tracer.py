"""
PlatformTracer - основной класс для создания spans.

OpenTelemetry spans используются для трейсинга выполнения агентов.
Ошибки "Failed to detach context" при закрытии async generators безопасны и подавляются.
"""

from __future__ import annotations

import hashlib
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
_process_tracing_service_name: Optional[str] = None


def set_tracing_service_name(name: str) -> None:
    """Имя процесса для колонки service_name (один раз при старте сервиса/воркера)."""
    global _process_tracing_service_name
    _process_tracing_service_name = name


def _resolve_tracing_service_name() -> str:
    if _process_tracing_service_name:
        return _process_tracing_service_name
    from core.config import get_settings

    return get_settings().server.name


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

        all_attrs = dict(span.attributes) if span.attributes else {}
        if extra_attrs:
            all_attrs.update(extra_attrs)

        if trace_ctx:
            if trace_ctx.flow_id and attr.ATTR_FLOW_ID not in all_attrs:
                all_attrs[attr.ATTR_FLOW_ID] = trace_ctx.flow_id
            if trace_ctx.task_id and attr.ATTR_TASK_ID not in all_attrs:
                all_attrs[attr.ATTR_TASK_ID] = trace_ctx.task_id
            if trace_ctx.context_id and attr.ATTR_CONTEXT_ID not in all_attrs:
                all_attrs[attr.ATTR_CONTEXT_ID] = trace_ctx.context_id
            if trace_ctx.branch_id and attr.ATTR_BRANCH_ID not in all_attrs:
                all_attrs[attr.ATTR_BRANCH_ID] = trace_ctx.branch_id
            if trace_ctx.channel and attr.ATTR_CHANNEL not in all_attrs:
                all_attrs[attr.ATTR_CHANNEL] = trace_ctx.channel
            if trace_ctx.is_resume and attr.ATTR_IS_RESUME not in all_attrs:
                all_attrs[attr.ATTR_IS_RESUME] = trace_ctx.is_resume

        company_id: Optional[str] = None
        namespace: Optional[str] = None
        from core.context import get_context

        app_ctx = get_context()
        if app_ctx:
            if app_ctx.active_company:
                company_id = app_ctx.active_company.company_id
            namespace = app_ctx.active_namespace
            if company_id and attr.ATTR_TENANT_COMPANY_ID not in all_attrs:
                all_attrs[attr.ATTR_TENANT_COMPANY_ID] = company_id
            if namespace and attr.ATTR_TENANT_NAMESPACE not in all_attrs:
                all_attrs[attr.ATTR_TENANT_NAMESPACE] = namespace
            ctx_user_id = app_ctx.user.user_id if app_ctx.user else None
            if (
                ctx_user_id is not None
                and str(ctx_user_id).strip() != ""
                and attr.ATTR_USER_ID not in all_attrs
            ):
                all_attrs[attr.ATTR_USER_ID] = str(ctx_user_id).strip()

        cid_attr = all_attrs.get(attr.ATTR_TENANT_COMPANY_ID)
        if cid_attr is not None:
            cid_str = str(cid_attr).strip()
            if cid_str != "":
                company_id = cid_str
        ns_attr = all_attrs.get(attr.ATTR_TENANT_NAMESPACE)
        if ns_attr is not None:
            ns_str = str(ns_attr).strip()
            if ns_str != "":
                namespace = ns_str

        channel_val = trace_ctx.channel if trace_ctx else all_attrs.get(attr.ATTR_CHANNEL)

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
            "service_name": _resolve_tracing_service_name(),
            "company_id": company_id,
            "namespace": namespace,
            "user_id": trace_ctx.user_id if trace_ctx else all_attrs.get(attr.ATTR_USER_ID),
            "user_name": trace_ctx.user_name if trace_ctx else None,
            "user_groups": trace_ctx.user_groups if trace_ctx else None,
            "session_auth": trace_ctx.session_auth if trace_ctx else None,
            "session_agent": trace_ctx.session_agent if trace_ctx else None,
            "channel": channel_val,
            "event_type": all_attrs.get(attr.ATTR_EVENT_TYPE),
            "resource_type": all_attrs.get(attr.ATTR_RESOURCE_TYPE),
            "resource_id": all_attrs.get(attr.ATTR_RESOURCE_ID),
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
        flow_id: Optional[str] = None,
        branch_id: Optional[str] = None,
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
            flow_id=flow_id,
            branch_id=branch_id,
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
        if trace_ctx.flow_id:
            attrs[attr.ATTR_FLOW_ID] = trace_ctx.flow_id
        if trace_ctx.branch_id:
            attrs[attr.ATTR_BRANCH_ID] = trace_ctx.branch_id
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
        flow_id: str,
        entry_node: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения flow."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_FLOW_ID] = flow_id
        attributes[attr.ATTR_FLOW_ENTRY] = entry_node

        with self._otel_tracer.start_as_current_span(
            name=f"flow.{flow_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"flow.{flow_id}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def resource_root_span(
        self,
        operation_name: str,
        *,
        resource_type: str,
        resource_id: str,
        event_type: str = "resource.session",
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """
        Корневой span сущности (чат, сессия flow, заметка): дочерние spans через вложенные
        context manager'ы PlatformTracer получают parent_span_id и общий trace_id (дерево OTEL).
        Колонки event_type / resource_type / resource_id — выборки «журнал по сущности».
        """
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_RESOURCE_TYPE] = resource_type
        attributes[attr.ATTR_RESOURCE_ID] = resource_id
        attributes[attr.ATTR_EVENT_TYPE] = event_type

        with self._otel_tracer.start_as_current_span(
            name=operation_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, operation_name, "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def platform_operation_span(
        self,
        operation_name: str,
        *,
        event_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        trace_ctx: Optional[TraceContext] = None,
        extra_attributes: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Span, None]:
        """
        Универсальный span значимой операции сервиса (RAG, Sync, CRM, …).
        operation_name: стабильный идентификатор вида service.area.action.
        """
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        if event_type:
            attributes[attr.ATTR_EVENT_TYPE] = event_type
        if resource_type:
            attributes[attr.ATTR_RESOURCE_TYPE] = resource_type
        if resource_id:
            attributes[attr.ATTR_RESOURCE_ID] = resource_id
        if extra_attributes:
            attributes.update(extra_attributes)

        with self._otel_tracer.start_as_current_span(
            name=operation_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, operation_name, "INTERNAL", start_time, trace_ctx)

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
    async def llm_node_span(
        self,
        node_label: str,
        flow_id: Optional[str] = None,
        model: Optional[str] = None,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span на весь ReAct-цикл llm_node (LLM + tools)."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_LLM_NODE_LABEL] = node_label
        if flow_id:
            attributes[attr.ATTR_FLOW_ID] = flow_id
        if model:
            attributes[attr.ATTR_LLM_MODEL] = model

        with self._otel_tracer.start_as_current_span(
            name=f"llm_node.{node_label}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"llm_node.{node_label}", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def react_iteration_span(
        self,
        iteration: int,
        node_label: str,
        trace_ctx: Optional[TraceContext] = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для одной итерации ReAct цикла."""
        if not is_tracing_enabled():
            yield trace.get_current_span()
            return

        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_REACT_ITERATION] = iteration
        attributes[attr.ATTR_LLM_NODE_LABEL] = node_label

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
        llm_provider: Optional[str] = None,
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
        if llm_provider:
            attributes[attr.ATTR_LLM_PROVIDER] = llm_provider

        with self._otel_tracer.start_as_current_span(
            name=f"llm.{model}",
            kind=SpanKind.CLIENT,
            attributes=attributes,
        ) as span:
            try:
                yield span
            finally:
                await self._save_span(span, f"llm.{model}", "CLIENT", start_time, trace_ctx)

    def record_llm_request(
        self,
        span: Span,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Записывает полный LLM request в span.
        
        Args:
            span: OpenTelemetry span
            messages: Список сообщений в формате OpenAI
            tools: Список tools schemas
            response_format: Structured output schema (json_schema)
        """
        request_data = {
            "messages": messages,
            "tools": tools or [],
        }
        if response_format:
            request_data["response_format"] = response_format
        request_str = json.dumps(request_data, ensure_ascii=False, default=str)
        span.set_attribute(attr.ATTR_LLM_REQUEST, request_str)

    def record_llm_response(
        self,
        span: Span,
        input_tokens: int,
        output_tokens: int,
        has_tool_calls: bool,
        duration_ms: float,
        response_content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        llm_provider: Optional[str] = None,
        provider_reported_cost: Optional[float] = None,
        provider_upstream_inference_cost: Optional[float] = None,
        settlement_quantity_rub: Optional[int] = None,
    ) -> None:
        """Записывает результат LLM вызова в span и помечает для billing settlement."""
        total_tokens = input_tokens + output_tokens
        span.set_attributes(
            {
                attr.ATTR_LLM_INPUT_TOKENS: input_tokens,
                attr.ATTR_LLM_OUTPUT_TOKENS: output_tokens,
                attr.ATTR_LLM_TOTAL_TOKENS: total_tokens,
                attr.ATTR_LLM_HAS_TOOL_CALLS: has_tool_calls,
                attr.ATTR_LLM_DURATION_MS: duration_ms,
            }
        )
        if llm_provider:
            span.set_attribute(attr.ATTR_LLM_PROVIDER, llm_provider)
        if provider_reported_cost is not None:
            span.set_attribute(attr.ATTR_LLM_PROVIDER_REPORTED_COST, provider_reported_cost)
        if provider_upstream_inference_cost is not None:
            span.set_attribute(
                attr.ATTR_LLM_PROVIDER_UPSTREAM_INFERENCE_COST,
                provider_upstream_inference_cost,
            )
        if settlement_quantity_rub is not None:
            if settlement_quantity_rub < 1:
                raise ValueError("settlement_quantity_rub должна быть >= 1")
            span.set_attribute(attr.ATTR_BILLING_SETTLEMENT_QUANTITY_RUB, settlement_quantity_rub)

        span_attrs = getattr(span, "attributes", None) or {}
        model = span_attrs.get(attr.ATTR_LLM_MODEL, "unknown")
        span.set_attributes(
            {
                attr.ATTR_BILLING_USAGE_TYPE: "llm_request",
                attr.ATTR_BILLING_RESOURCE_NAME: f"llm:{model}",
                attr.ATTR_BILLING_QUANTITY: total_tokens,
                attr.ATTR_BILLING_PENDING_SETTLEMENT: True,
            }
        )
        
        if response_content is not None or tool_calls:
            response_data = {
                "content": response_content,
                "tool_calls": tool_calls or [],
            }
            response_str = json.dumps(response_data, ensure_ascii=False, default=str)
            span.set_attribute(attr.ATTR_LLM_RESPONSE, response_str)

    @asynccontextmanager
    async def tool_call_span(
        self,
        tool_name: str,
        tool_call_id: str,
        args: Dict[str, Any],
        nested_flow_tool: bool = False,
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
        attributes[attr.ATTR_TOOL_IS_AGENT] = nested_flow_tool
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

