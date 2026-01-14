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
from .provider import setup_tracing, is_tracing_enabled, set_tracing_enabled
from .tracer import PlatformTracer, get_tracer, set_span_repository
from .middleware import TracingMiddleware
from .repository import SpanRepository

__all__ = [
    "TracingConfig",
    "TraceContext",
    "get_current_trace_context",
    "set_current_trace_context",
    "setup_tracing",
    "is_tracing_enabled",
    "set_tracing_enabled",
    "PlatformTracer",
    "get_tracer",
    "set_span_repository",
    "TracingMiddleware",
    "SpanRepository",
]

