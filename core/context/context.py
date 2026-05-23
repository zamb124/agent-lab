"""
Глобальный асинхронный контекст для запросов.
Использует contextvars для передачи контекста через все async вызовы.
"""

import contextvars
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.models.context_models import Context
    from core.models.identity_models import Company


_context: contextvars.ContextVar[Optional["Context"]] = contextvars.ContextVar(
    "context", default=None
)

_current_channel: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
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


def require_context() -> "Context":
    """Возвращает текущий контекст или падает, если request/job scope не установлен."""
    context = get_context()
    if context is None:
        raise RuntimeError("Context is required but is not set")
    return context


def require_active_company() -> "Company":
    """Возвращает активную компанию текущего контекста или падает."""
    context = require_context()
    company = context.active_company
    if company is None:
        raise RuntimeError("Active company is required but is not set in context")
    return company


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


def get_current_channel() -> Any | None:
    """
    Получает текущий канал коммуникации.

    Returns:
        Текущий канал или None
    """
    return _current_channel.get()
