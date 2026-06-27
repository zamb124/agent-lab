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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SDKSpan
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

import core.tracing.attributes as attr
from core.config import get_settings
from core.context import get_context
from core.logging import get_logger
from core.tracing.models import TraceSpanEvent, TraceSpanWrite
from core.types import (
    JsonObject,
    JsonValue,
    OtelAttributes,
    OtelAttributeValue,
    otel_attributes_to_json_object,
    require_json_object,
)

if TYPE_CHECKING:
    from core.state import ExecutionState
from .context import TraceContext
from .provider import ensure_tracer_provider

if TYPE_CHECKING:
    from .repository import SpanRepository

logger = get_logger(__name__)

def _span_event_timestamp(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc).isoformat()


def _sdk_span(span: Span) -> SDKSpan:
    if not isinstance(span, SDKSpan):
        raise TypeError("OpenTelemetry SDK span is required for platform tracing persistence")
    return span


def _serialize_span_events(readable_span: SDKSpan) -> list[TraceSpanEvent]:
    events: list[TraceSpanEvent] = []
    for event in readable_span.events:
        event_attributes = otel_attributes_to_json_object(event.attributes)
        events.append(
            TraceSpanEvent(
                name=event.name,
                timestamp=_span_event_timestamp(event.timestamp),
                attributes=event_attributes,
            )
        )
    return events


def _is_control_flow_exception(error: Exception) -> bool:
    exc_type = type(error)
    return exc_type.__name__ in {
        "FlowInterrupt",
        "BreakpointInterrupt",
        "FlowCancelled",
    } and exc_type.__module__.startswith("apps.flows.")


# При закрытии async generators (GeneratorExit) OpenTelemetry пытается detach
# контекст который был создан в другом async контексте. Это безопасно игнорировать.
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
logging.getLogger("opentelemetry.trace").addFilter(
    lambda record: "Failed to detach context" not in record.getMessage()
)
logging.getLogger("opentelemetry.sdk.trace").addFilter(
    lambda record: "Failed to detach context" not in record.getMessage()
)

_tracer: PlatformTracer | None = None
_span_repository: SpanRepository | None = None
_process_tracing_service_name: str | None = None


def _span_attribute(span: Span, key: str) -> OtelAttributeValue | None:
    span_attrs = _sdk_span(span).attributes
    if span_attrs is None:
        return None
    return span_attrs.get(key)


def _optional_json_string(attributes: JsonObject, key: str) -> str | None:
    value = attributes.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} должен быть строкой")
    return value


def _llm_operation_name(span: Span, fallback_model: str) -> str:
    model = _span_attribute(span, attr.ATTR_LLM_MODEL)
    if isinstance(model, str) and model.strip():
        return f"llm.{model.strip()}"
    return f"llm.{fallback_model}"


def set_tracing_service_name(name: str) -> None:
    """Имя процесса для колонки service_name (один раз при старте сервиса/воркера)."""
    global _process_tracing_service_name
    _process_tracing_service_name = name


def _resolve_tracing_service_name() -> str:
    if _process_tracing_service_name:
        return _process_tracing_service_name
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
        self._otel_tracer: Tracer = ensure_tracer_provider(service_name).get_tracer(service_name)
        self._service_name: str = service_name

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
        trace_ctx: TraceContext | None,
        extra_attrs: OtelAttributes | None = None,
    ) -> None:
        """Сохраняет span в PostgreSQL."""
        if _span_repository is None:
            logger.debug("tracing.span_not_persisted", operation_name=operation_name)
            return

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        readable_span = _sdk_span(span)

        parent_ctx = readable_span.parent
        parent_span_id = format(parent_ctx.span_id, "016x") if parent_ctx else None

        status = "OK"
        status_message = None
        if readable_span.status.status_code == StatusCode.ERROR:
            status = "ERROR"
            status_message = readable_span.status.description

        all_attrs = require_json_object(
            otel_attributes_to_json_object(readable_span.attributes),
            "span.attributes",
        )
        if extra_attrs:
            all_attrs.update(otel_attributes_to_json_object(extra_attrs))

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

        company_id: str | None = None
        namespace: str | None = None

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

        channel_val = trace_ctx.channel if trace_ctx else _optional_json_string(all_attrs, attr.ATTR_CHANNEL)

        span_data = TraceSpanWrite(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            kind=kind,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            status_message=status_message,
            service_name=_resolve_tracing_service_name(),
            company_id=company_id,
            namespace=namespace,
            user_id=trace_ctx.user_id if trace_ctx else _optional_json_string(all_attrs, attr.ATTR_USER_ID),
            user_name=trace_ctx.user_name if trace_ctx else None,
            user_groups=trace_ctx.user_groups if trace_ctx else None,
            session_auth=trace_ctx.session_auth if trace_ctx else None,
            session_agent=trace_ctx.session_agent if trace_ctx else None,
            channel=channel_val,
            event_type=_optional_json_string(all_attrs, attr.ATTR_EVENT_TYPE),
            resource_type=_optional_json_string(all_attrs, attr.ATTR_RESOURCE_TYPE),
            resource_id=_optional_json_string(all_attrs, attr.ATTR_RESOURCE_ID),
            attributes=all_attrs,
            events=_serialize_span_events(readable_span),
        )

        await _span_repository.save_span(span_data)

    def create_trace_context(
        self,
        user_id: str | None = None,
        user_name: str | None = None,
        user_groups: list[str] | None = None,
        session_auth: str | None = None,
        session_agent: str | None = None,
        task_id: str | None = None,
        context_id: str | None = None,
        flow_id: str | None = None,
        branch_id: str | None = None,
        channel: str | None = None,
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

    def fork_trace_context(
        self,
        base: TraceContext,
        *,
        parent_span_id: str | None = None,
        **updates: JsonValue,
    ) -> TraceContext:
        """Новый span в том же trace_id (handoff child / parent resume)."""
        _, span_id = self._generate_ids()
        merged_parent_span_id = parent_span_id if parent_span_id is not None else base.span_id
        return TraceContext.merge_from(
            base,
            trace_id=base.trace_id,
            span_id=span_id,
            parent_span_id=merged_parent_span_id,
            **updates,
        )

    def continue_trace_context(
        self,
        trace_id: str,
        *,
        parent_span_id: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        user_groups: list[str] | None = None,
        session_auth: str | None = None,
        session_agent: str | None = None,
        task_id: str | None = None,
        context_id: str | None = None,
        flow_id: str | None = None,
        branch_id: str | None = None,
        channel: str | None = None,
        is_resume: bool = False,
    ) -> TraceContext:
        """Продолжение существующего trace_id (HTTP reply в handoff child)."""
        _, span_id = self._generate_ids()
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
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

    def _base_attributes(self, trace_ctx: TraceContext | None) -> dict[str, OtelAttributeValue]:
        """Возвращает базовые атрибуты для всех spans."""
        if trace_ctx is None:
            return {}

        attrs: dict[str, OtelAttributeValue] = {}
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
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для HTTP-запроса (message/send, message/stream)."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes["http.method"] = method

        with self._otel_tracer.start_as_current_span(
            name=f"request.{method}",
            kind=SpanKind.SERVER,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(span, f"request.{method}", "SERVER", start_time, trace_ctx)

    @asynccontextmanager
    async def flow_span(
        self,
        flow_id: str,
        entry_node: str,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения flow."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_FLOW_ID] = flow_id
        attributes[attr.ATTR_FLOW_ENTRY] = entry_node

        with self._otel_tracer.start_as_current_span(
            name=f"flow.{flow_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
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
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """
        Корневой span сущности (чат, сессия flow, заметка): дочерние spans через вложенные
        context manager'ы PlatformTracer получают parent_span_id и общий trace_id (дерево OTEL).
        Колонки event_type / resource_type / resource_id — выборки «журнал по сущности».
        """
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_RESOURCE_TYPE] = resource_type
        attributes[attr.ATTR_RESOURCE_ID] = resource_id
        attributes[attr.ATTR_EVENT_TYPE] = event_type

        with self._otel_tracer.start_as_current_span(
            name=operation_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(span, operation_name, "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def platform_operation_span(
        self,
        operation_name: str,
        *,
        event_type: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_ctx: TraceContext | None = None,
        extra_attributes: OtelAttributes | None = None,
    ) -> AsyncGenerator[Span, None]:
        """
        Универсальный span значимой операции сервиса (RAG, Sync, CRM, …).
        operation_name: стабильный идентификатор вида service.area.action.
        """
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
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(span, operation_name, "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def node_span(
        self,
        node_id: str,
        node_type: str,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для выполнения ноды."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_NODE_ID] = node_id
        attributes[attr.ATTR_NODE_TYPE] = node_type

        with self._otel_tracer.start_as_current_span(
            name=f"node.{node_type}.{node_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(
                    span, f"node.{node_type}.{node_id}", "INTERNAL", start_time, trace_ctx
                )

    @asynccontextmanager
    async def llm_node_span(
        self,
        node_label: str,
        flow_id: str | None = None,
        model: str | None = None,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span на весь ReAct-цикл llm_node (LLM + tools)."""
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
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(
                    span, f"llm_node.{node_label}", "INTERNAL", start_time, trace_ctx
                )

    @asynccontextmanager
    async def react_iteration_span(
        self,
        iteration: int,
        node_label: str,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для одной итерации ReAct цикла."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_REACT_ITERATION] = iteration
        attributes[attr.ATTR_LLM_NODE_LABEL] = node_label

        with self._otel_tracer.start_as_current_span(
            name=f"react.iteration.{iteration}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(
                    span, f"react.iteration.{iteration}", "INTERNAL", start_time, trace_ctx
                )

    @asynccontextmanager
    async def llm_call_span(
        self,
        model: str,
        messages_count: int,
        tools_count: int,
        trace_ctx: TraceContext | None = None,
        llm_provider: str | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для вызова LLM."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_LLM_MODEL] = model
        attributes[attr.ATTR_LLM_REQUESTED_MODEL] = model
        attributes["llm.messages_count"] = messages_count
        attributes["llm.tools_count"] = tools_count
        attributes[attr.ATTR_LLM_STREAM] = True
        if llm_provider:
            attributes[attr.ATTR_LLM_PROVIDER] = llm_provider

        with self._otel_tracer.start_as_current_span(
            name=f"llm.{model}",
            kind=SpanKind.CLIENT,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(
                    span,
                    _llm_operation_name(span, model),
                    "CLIENT",
                    start_time,
                    trace_ctx,
                )

    def record_llm_request(
        self,
        span: Span,
        messages: list[JsonObject],
        tools: list[JsonObject] | None = None,
        response_format: JsonObject | None = None,
    ) -> None:
        """
        Записывает полный LLM request в span.

        Аргументы:
            span: OpenTelemetry span
            messages: Список сообщений в формате OpenAI
            tools: Список tools schemas
            response_format: Structured output schema (json_schema)
        """
        request_data: JsonObject = {
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
        response_content: str | None = None,
        tool_calls: list[JsonObject] | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        candidate_source: str | None = None,
        provider_reported_cost: float | None = None,
        provider_upstream_inference_cost: float | None = None,
        settlement_quantity_rub: int | None = None,
        billing_resource_name: str | None = None,
        cost_origin: str | None = None,
        custom_provider_id: str | None = None,
        llm_context: JsonObject | None = None,
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
        resolved_model = llm_model.strip() if llm_model is not None else None
        if resolved_model:
            span.set_attribute(attr.ATTR_LLM_MODEL, resolved_model)
        if llm_provider:
            span.set_attribute(attr.ATTR_LLM_PROVIDER, llm_provider)
        if candidate_source:
            span.set_attribute(attr.ATTR_LLM_CANDIDATE_SOURCE, candidate_source)
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

        model_attribute = _span_attribute(span, attr.ATTR_LLM_MODEL)
        model = resolved_model
        if model is None and isinstance(model_attribute, str) and model_attribute:
            model = model_attribute
        if model is None:
            model = "unknown"
        resource_name = billing_resource_name if billing_resource_name else f"llm:{model}"
        span.set_attributes(
            {
                attr.ATTR_BILLING_USAGE_TYPE: "llm_request",
                attr.ATTR_BILLING_RESOURCE_NAME: resource_name,
                attr.ATTR_BILLING_QUANTITY: total_tokens,
                attr.ATTR_BILLING_PENDING_SETTLEMENT: True,
            }
        )
        if cost_origin is not None:
            span.set_attribute(attr.ATTR_BILLING_COST_ORIGIN, cost_origin)
        if custom_provider_id is not None:
            span.set_attribute(attr.ATTR_BILLING_CUSTOM_PROVIDER_ID, custom_provider_id)
        if llm_context is not None:
            self._record_llm_context(span, llm_context)

        if response_content is not None or tool_calls:
            response_data = {
                "content": response_content,
                "tool_calls": tool_calls or [],
            }
            response_str = json.dumps(response_data, ensure_ascii=False, default=str)
            span.set_attribute(attr.ATTR_LLM_RESPONSE, response_str)

    def _record_llm_context(self, span: Span, llm_context: JsonObject) -> None:
        span.set_attribute(attr.ATTR_LLM_CONTEXT_ENABLED, True)
        usage = llm_context.get("usage")
        if isinstance(usage, dict):
            total_input = usage.get("total_input_tokens")
            if isinstance(total_input, int) and not isinstance(total_input, bool):
                span.set_attribute(attr.ATTR_LLM_CONTEXT_TOTAL_INPUT_TOKENS, total_input)
            max_input = usage.get("max_input_tokens")
            if isinstance(max_input, int) and not isinstance(max_input, bool):
                span.set_attribute(attr.ATTR_LLM_CONTEXT_MAX_INPUT_TOKENS, max_input)
            model_context_length = usage.get("model_context_length")
            if isinstance(model_context_length, int) and not isinstance(model_context_length, bool):
                span.set_attribute(
                    attr.ATTR_LLM_CONTEXT_MODEL_CONTEXT_LENGTH,
                    model_context_length,
                )
        selected = llm_context.get("selected_blocks")
        if isinstance(selected, list):
            span.set_attribute(attr.ATTR_LLM_CONTEXT_SELECTED_BLOCKS_COUNT, len(selected))
        dropped = llm_context.get("dropped_blocks")
        if isinstance(dropped, list):
            span.set_attribute(attr.ATTR_LLM_CONTEXT_DROPPED_BLOCKS_COUNT, len(dropped))
        span.set_attribute(
            attr.ATTR_LLM_CONTEXT,
            json.dumps(llm_context, ensure_ascii=False, default=str),
        )

    @asynccontextmanager
    async def tool_call_span(
        self,
        tool_name: str,
        tool_call_id: str,
        args: JsonObject,
        nested_flow_tool: bool = False,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для вызова tool."""
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
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(span, f"tool.{tool_name}", "INTERNAL", start_time, trace_ctx)

    def record_tool_result(
        self,
        span: Span,
        result: JsonValue | None,
        duration_ms: float,
        error: str | None = None,
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
        """Записывает projection snapshot в span."""
        # Конвертируем ExecutionState в dict для JSON сериализации
        state_dict = require_json_object(
            state.model_dump(mode="json", exclude_none=False),
            "state.snapshot",
        )

        snapshot = {
            k: v for k, v in state_dict.items() if not k.startswith("__") or k == "__tools__"
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
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для interrupt (ask_user)."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_INTERRUPT_QUESTION] = question[:200]
        attributes[attr.ATTR_INTERRUPT_TOOL] = tool_name
        attributes[attr.ATTR_INTERRUPT_PATH_DEPTH] = path_depth

        with self._otel_tracer.start_as_current_span(
            name="interrupt.ask_user",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(span, "interrupt.ask_user", "INTERNAL", start_time, trace_ctx)

    @asynccontextmanager
    async def prompt_build_span(
        self,
        node_id: str,
        template: str,
        variables: JsonObject,
        trace_ctx: TraceContext | None = None,
    ) -> AsyncGenerator[Span, None]:
        """Span для сборки системного промпта."""
        start_time = datetime.now(timezone.utc)
        attributes = self._base_attributes(trace_ctx)
        attributes[attr.ATTR_PROMPT_NODE_ID] = node_id
        attributes[attr.ATTR_PROMPT_TEMPLATE_LENGTH] = len(template)
        attributes[attr.ATTR_PROMPT_VARIABLES_COUNT] = len(variables)

        # Фильтруем переменные - оставляем только скалярные значения
        safe_vars = {
            k: v
            for k, v in variables.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        variables_str = json.dumps(safe_vars, ensure_ascii=False, default=str)[:2000]
        attributes[attr.ATTR_PROMPT_VARIABLES] = variables_str

        with self._otel_tracer.start_as_current_span(
            name=f"prompt.build.{node_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as exc:
                self.set_error(span, exc)
                raise
            finally:
                await self._save_span(
                    span, f"prompt.build.{node_id}", "INTERNAL", start_time, trace_ctx
                )

    def record_prompt_result(
        self,
        span: Span,
        rendered_prompt: str,
    ) -> None:
        """Записывает результат сборки промпта в span."""
        prompt_hash = hashlib.md5(rendered_prompt.encode()).hexdigest()
        span.set_attributes(
            {
                attr.ATTR_PROMPT_RENDERED_LENGTH: len(rendered_prompt),
                attr.ATTR_PROMPT_HASH: prompt_hash,
            }
        )

    def get_current_trace_context(self) -> TraceContext | None:
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
        if _is_control_flow_exception(error):
            return
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.set_attribute(attr.ATTR_ERROR_MESSAGE, str(error))
        span.set_attribute(attr.ATTR_ERROR_TYPE, type(error).__name__)
        span.record_exception(error)
