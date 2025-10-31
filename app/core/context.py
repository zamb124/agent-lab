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
    """Устанавливает контекст с автоматической инициализацией контейнера для event loop

    Контейнер создается один раз на event loop и разделяется между всеми контекстами.

    Использование:
        await set_context(context)
    """
    # Инициализируем контейнер для текущего event loop (если еще не создан)
    from app.core.container import get_container_for_loop
    await get_container_for_loop()

    _context.set(context)


def get_context() -> Optional["Context"]:
    """Получает текущий контекст"""
    return _context.get()


def clear_context() -> None:
    """Очищает контекст"""
    _context.set(None)
