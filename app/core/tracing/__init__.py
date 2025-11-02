"""
Модуль трейсинга на базе OpenTelemetry.
"""

from app.core.tracing.callback_handler import OpenTelemetryCallbackHandler
from app.core.tracing.callback_factory import (
    get_otel_callback_handler,
    get_callbacks_for_agent,
)

__all__ = [
    "OpenTelemetryCallbackHandler",
    "get_otel_callback_handler",
    "get_callbacks_for_agent",
]


