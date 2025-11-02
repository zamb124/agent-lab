"""
Глобальный асинхронный контекст для запросов.
Использует contextvars для передачи контекста через все async вызовы.
"""

import contextvars
import asyncio
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.context_models import Context


_context: contextvars.ContextVar[Optional["Context"]] = contextvars.ContextVar(
    "context", default=None
)


def set_context(context: "Context") -> None:
    """Устанавливает контекст

    Использование:
        set_context(context)
    """
    _context.set(context)


def get_context() -> Optional["Context"]:
    """Получает текущий контекст"""
    return _context.get()


def clear_context() -> None:
    """Очищает контекст"""
    _context.set(None)
