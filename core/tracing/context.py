"""
TraceContext для propagation между процессами (API → TaskIQ Worker).
"""

from contextvars import ContextVar
from typing import Any, Optional

from pydantic import BaseModel, Field

# ContextVar для хранения trace context в worker
_trace_context_var: ContextVar[dict[str, Any] | None] = ContextVar("trace_context", default=None)


def get_current_trace_context() -> dict[str, Any] | None:
    """Получает текущий trace context из ContextVar."""
    return _trace_context_var.get()


def set_current_trace_context(trace_context: dict[str, Any] | None) -> None:
    """Устанавливает trace context в ContextVar."""
    _trace_context_var.set(trace_context)


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

    def to_dict(self) -> dict[str, Any]:
        """Сериализует контекст для передачи через TaskIQ."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceContext":
        """Восстанавливает контекст из dict."""
        return cls.model_validate(data)

    def to_traceparent(self) -> str:
        """
        W3C Trace Context формат.

        Format: {version}-{trace-id}-{parent-id}-{trace-flags}
        """
        return f"00-{self.trace_id}-{self.span_id}-01"

    @classmethod
    def from_traceparent(cls, traceparent: str) -> Optional["TraceContext"]:
        """Парсит W3C Trace Context."""
        parts = traceparent.split("-")
        if len(parts) != 4:
            return None
        return cls(trace_id=parts[1], span_id=parts[2])

