"""
TraceContext для propagation между процессами (API → TaskIQ Worker).
"""

from __future__ import annotations

from contextvars import ContextVar

from pydantic import BaseModel, Field

from core.types import JsonObject

# ContextVar для хранения trace context в worker
_trace_context_var: ContextVar[JsonObject | None] = ContextVar("trace_context", default=None)


def get_current_trace_context() -> JsonObject | None:
    """Получает текущий trace context из ContextVar."""
    return _trace_context_var.get()


def set_current_trace_context(trace_context: JsonObject | None) -> None:
    """Устанавливает trace context в ContextVar."""
    _ = _trace_context_var.set(trace_context)


class TraceContext(BaseModel):
    """
    Контекст трейса для передачи между процессами.

    Передается через TaskIQ для сохранения связи между API запросом и worker.
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    # Данные пользователя для записи в spans
    user_id: str | None = None
    user_name: str | None = None
    user_groups: list[str] = Field(default_factory=list)

    # Сессии
    session_auth: str | None = None
    session_agent: str | None = None

    # Идентификаторы запроса
    task_id: str | None = None
    context_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    channel: str | None = None
    is_resume: bool = False

    def to_dict(self) -> JsonObject:
        """Сериализует контекст для передачи через TaskIQ."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "user_groups": self.user_groups,
            "session_auth": self.session_auth,
            "session_agent": self.session_agent,
            "task_id": self.task_id,
            "context_id": self.context_id,
            "flow_id": self.flow_id,
            "branch_id": self.branch_id,
            "channel": self.channel,
            "is_resume": self.is_resume,
        }

    @classmethod
    def from_dict(cls, data: JsonObject) -> "TraceContext":
        """Восстанавливает контекст из dict."""
        return cls.model_validate(data)

    def to_traceparent(self) -> str:
        """
        W3C Trace Context формат.

        Format: {version}-{trace-id}-{parent-id}-{trace-flags}
        """
        return f"00-{self.trace_id}-{self.span_id}-01"

    @classmethod
    def from_traceparent(cls, traceparent: str) -> TraceContext | None:
        """Парсит W3C Trace Context."""
        parts = traceparent.split("-")
        if len(parts) != 4:
            return None
        return cls(trace_id=parts[1], span_id=parts[2])
