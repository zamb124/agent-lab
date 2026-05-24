"""
OpenTelemetry трейсинг для Platform.

Публичный API:
- setup_tracing() - инициализация трейсинга
- get_tracer() - получение PlatformTracer
- TraceContext - контекст для propagation через TaskIQ
- get_current_trace_context() - получить trace context из ContextVar
- set_current_trace_context() - установить trace context в ContextVar
"""

from .config import TracingConfig
from .context import TraceContext, get_current_trace_context, set_current_trace_context
from .middleware import TracingMiddleware
from .models import (
    BillingSettlementSpan,
    TraceSearchResult,
    TraceSpanEvent,
    TraceSpanRecord,
    TraceSpanWrite,
)
from .operation_span import traced_operation
from .provider import is_tracing_enabled, set_tracing_enabled, setup_tracing, shutdown_tracing
from .repository import SpanRepository
from .tracer import (
    PlatformTracer,
    get_tracer,
    set_span_repository,
    set_tracing_service_name,
)

__all__ = [
    "TracingConfig",
    "TraceContext",
    "get_current_trace_context",
    "set_current_trace_context",
    "setup_tracing",
    "is_tracing_enabled",
    "set_tracing_enabled",
    "shutdown_tracing",
    "PlatformTracer",
    "get_tracer",
    "set_span_repository",
    "set_tracing_service_name",
    "TracingMiddleware",
    "BillingSettlementSpan",
    "TraceSearchResult",
    "TraceSpanEvent",
    "TraceSpanRecord",
    "TraceSpanWrite",
    "SpanRepository",
    "traced_operation",
]
