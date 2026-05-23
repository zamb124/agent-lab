"""
Лог-контекст: bind/unbind/clear поверх structlog.contextvars.

Лог-контекст полностью отделен от бизнес-контекста (core.context.Context):
- core.context.Context используется бизнес-логикой (user, company, language).
- core.logging.context биндит структурированные поля в каждый лог-вывод.

Любой код, который попадает на стек обработки запроса/задачи, видит эти
поля автоматически, без явного прокидывания.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import cast

import structlog


def bind_log_context(**fields: object) -> None:
    """
    Добавить поля в лог-контекст текущей contextvar-копии.

    None-значения не биндятся. Пустые строки тоже игнорируются — это
    защита от записи бессмысленных полей.
    """
    cleaned = {key: value for key, value in fields.items() if value not in (None, "")}
    if not cleaned:
        return
    _ = structlog.contextvars.bind_contextvars(**cleaned)


def unbind_log_context(*keys: str) -> None:
    """Удалить указанные поля из лог-контекста (например, после завершения задачи)."""
    if not keys:
        return
    structlog.contextvars.unbind_contextvars(*keys)


def clear_log_context() -> None:
    """Полностью очистить лог-контекст текущей contextvar-копии."""
    structlog.contextvars.clear_contextvars()


def get_log_context() -> dict[str, object]:
    """Вернуть копию текущего лог-контекста (для отладки и тестов)."""
    return cast(dict[str, object], dict(structlog.contextvars.get_contextvars()))


def restore_log_context(snapshot: dict[str, object]) -> None:
    """Восстановить лог-контекст из snapshot (используется при выходе из скоупа)."""
    structlog.contextvars.clear_contextvars()
    if snapshot:
        _ = structlog.contextvars.bind_contextvars(**snapshot)


class LogContextScope:
    """
    Контекстный менеджер для временного биндинга полей.

    Использование::

        with LogContextScope(task_id="t-1", task_name="run_flow"):
            await do_work()
    """

    def __init__(self, **fields: object) -> None:
        self._fields: dict[str, object] = {
            key: value for key, value in fields.items() if value not in (None, "")
        }
        self._cm: AbstractContextManager[object] | None = None

    def __enter__(self) -> "LogContextScope":
        if self._fields:
            self._cm = cast(
                AbstractContextManager[object],
                structlog.contextvars.bound_contextvars(**self._fields),
            )
            _ = self._cm.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._cm is not None:
            _ = self._cm.__exit__(exc_type, exc, tb)
            self._cm = None

    async def __aenter__(self) -> "LogContextScope":
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.__exit__(exc_type, exc, tb)
