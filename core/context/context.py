"""
Глобальный асинхронный контекст для запросов.
Использует contextvars для передачи контекста через все async вызовы.
"""

import contextvars
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.context_models import Context


_context: contextvars.ContextVar[Optional["Context"]] = contextvars.ContextVar(
    "context", default=None
)

_current_channel: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "current_channel", default=None
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


def set_current_channel(channel: Any) -> None:
    """
    Устанавливает текущий канал коммуникации.
    
    Args:
        channel: Канал для установки (BaseChannel)
    """
    _current_channel.set(channel)


def get_current_channel() -> Optional[Any]:
    """
    Получает текущий канал коммуникации.
    
    Returns:
        Текущий канал или None
    """
    return _current_channel.get()
