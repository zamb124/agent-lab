"""
Глобальный асинхронный контекст для запросов.
Использует contextvars для передачи контекста через все async вызовы.
"""
import contextvars
from typing import Optional

from .models import Context


# Глобальная переменная контекста
_context: contextvars.ContextVar[Optional[Context]] = contextvars.ContextVar(
    'context', 
    default=None
)


def set_context(context: Context) -> None:
    """Устанавливает контекст"""
    _context.set(context)


def get_context() -> Optional[Context]:
    """Получает текущий контекст"""
    return _context.get()


def clear_context() -> None:
    """Очищает контекст"""
    _context.set(None)
