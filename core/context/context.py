"""
Глобальный асинхронный контекст для запросов.
Использует contextvars для передачи контекста через все async вызовы.
"""

import contextvars
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.context_models import Context


_context: contextvars.ContextVar[Optional["Context"]] = contextvars.ContextVar(
    "context", default=None
)


def set_context(context: "Context") -> None:
    """
    Устанавливает контекст.
    
    Args:
        context: Контекст для установки
    """
    _context.set(context)


def get_context() -> Optional["Context"]:
    """
    Получает текущий контекст.
    
    Returns:
        Текущий контекст или None
    """
    return _context.get()


def clear_context() -> None:
    """Очищает контекст"""
    _context.set(None)
