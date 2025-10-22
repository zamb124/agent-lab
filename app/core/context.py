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


async def set_context(context: "Context") -> None:
    """Устанавливает контекст с автоматической инициализацией сервисов
    
    Использование:
        await set_context(context)
    """
    if context.container is None:
        from app.core.container import initialize_context_services_async
        await initialize_context_services_async(context)
    _context.set(context)


def get_context() -> Optional["Context"]:
    """Получает текущий контекст"""
    return _context.get()


def clear_context() -> None:
    """Очищает контекст"""
    _context.set(None)
