"""
TraceContext для propagation между процессами (API → TaskIQ Worker).
"""

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ContextVar для хранения trace context в worker
_trace_context_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("trace_context", default=None)


def get_current_trace_context() -> Optional[Dict[str, Any]]:
    """Получает текущий trace context из ContextVar."""
    return _trace_context_var.get()


def set_current_trace_context(trace_context: Optional[Dict[str, Any]]) -> None:
    """Устанавливает trace context в ContextVar."""
    _trace_context_var.set(trace_context)


class TraceContext(BaseModel):
    """
    Контекст трейса для передачи между процессами.
    
    Передается через TaskIQ для сохранения связи между API запросом и worker.
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    
    # Данные пользователя для записи в spans
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_groups: List[str] = Field(default_factory=list)
    
    # Сессии
    session_auth: Optional[str] = None
    session_agent: Optional[str] = None
    
    # Идентификаторы запроса
    task_id: Optional[str] = None
    context_id: Optional[str] = None
    flow_id: Optional[str] = None
    branch_id: Optional[str] = None
    channel: Optional[str] = None
    is_resume: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Сериализует контекст для передачи через TaskIQ."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceContext":
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

