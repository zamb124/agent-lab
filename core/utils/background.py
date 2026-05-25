"""
Безопасный запуск фоновых корутин с прокидыванием лог-контекста.

Стандартный ``asyncio.create_task(coro)`` копирует contextvars автоматически
(в Python 3.11+), поэтому structlog.contextvars остаются доступны. Этот
модуль формализует контракт мега-правила:

1. Если фоновая задача стартует ИЗ request scope (HTTP/WS/TaskIQ) — она
   наследует request_id/trace_id/user_id/company_id текущего запроса. В
   логах фоновых операций виден тот же request_id, что у вызвавшего
   запроса, поэтому Loki/Grafana поиск по request_id даёт полную ленту
   событий, включая background.

2. Если задача стартует ИЗ системного scope (lifespan, scheduler, recovery
   loops) — обязателен явный ``background_kind`` (например ``startup``,
   ``recovery``, ``polling``). Хелпер сгенерирует request_id вида
   ``<kind>:<uuid>`` и trace_id вида ``<service>:<uuid>``, чтобы все логи
   фоновой задачи имели обязательные поля контракта.

Прямое использование ``asyncio.create_task(coro)`` запрещено CI-проверкой
``scripts/check_logging_canon.sh`` (за исключением белого списка
инфраструктурных файлов).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable
from typing import TypeVar

from core.config import get_settings
from core.logging import (
    LogContextScope,
    bind_log_context,
    enter_request_scope,
    exit_request_scope,
    get_log_context,
    get_logger,
)
from core.logging.attributes import (
    EVENT_BACKGROUND_TASK_FAILED,
    EVENT_BACKGROUND_TASK_STARTED,
)
from core.types import JsonObject, JsonValue, require_json_object

_logger = get_logger("platform.background")
BackgroundResultT = TypeVar("BackgroundResultT")


def run_with_log_context(
    coro: Awaitable[BackgroundResultT],
    *,
    name: str,
    background_kind: str | None = None,
    extra: JsonObject | None = None,
) -> asyncio.Task[BackgroundResultT]:
    """
    Запустить фоновую задачу, наследовав текущий лог-контекст.

    Args:
        coro: ожидаемая корутина (НЕ функция; уже вызванная — `do()`).
        name: стабильное имя задачи (видно в логах как background_task_name).
        background_kind: короткий префикс для генерации request_id, если
            задача стартует ИЗ системного скоупа (нет request_id в текущем
            лог-контексте). Например ``startup``, ``recovery``, ``polling``,
            ``cron``. Обязательно для системных запусков.
        extra: дополнительные поля для bind на время задачи.

    Returns:
        asyncio.Task. Результат корутины не возвращается; вызывающий код
        обязан забрать его сам, если нужен (через await task).

    Raises:
        ValueError: если name пустой или нет background_kind вне request scope.
    """
    if not name.strip():
        raise ValueError("background-task name обязателен и должен быть непустой строкой")

    snapshot = require_json_object(get_log_context(), "log.context")
    inherited_request_id = snapshot.get("request_id")
    inherited_trace_id = snapshot.get("trace_id")
    settings = get_settings()
    service_name = settings.server.name

    if not isinstance(inherited_request_id, str) or not inherited_request_id.strip():
        if not background_kind or not background_kind.strip():
            message = (
                f"run_with_log_context({name!r}): фоновая задача стартует вне "
                + "request scope, обязателен параметр background_kind "
                + "(например 'startup', 'recovery', 'polling')."
            )
            raise ValueError(message)
        prefix = background_kind.strip()
        inherited_request_id = f"{prefix}:{uuid.uuid4().hex}"

    if not isinstance(inherited_trace_id, str) or not inherited_trace_id.strip():
        prefix = (background_kind or "background").strip()
        inherited_trace_id = f"{prefix}:{uuid.uuid4().hex}"

    extra_bindings: JsonObject = {
        "background_task_name": name,
        "background_task_id": uuid.uuid4().hex,
    }
    if extra:
        extra_bindings.update({k: v for k, v in extra.items() if v not in (None, "")})

    user_id = _str_or_none(snapshot.get("user_id"))
    company_id = _str_or_none(snapshot.get("company_id"))

    async def runner() -> BackgroundResultT:
        token = enter_request_scope(
            request_id=inherited_request_id,
            trace_id=inherited_trace_id,
            service_name=service_name,
            user_id=user_id,
            company_id=company_id,
        )
        bind_log_context(**extra_bindings)
        _logger.info(EVENT_BACKGROUND_TASK_STARTED, background_task_name=name)
        try:
            return await coro
        except Exception as exc:
            _logger.exception(
                EVENT_BACKGROUND_TASK_FAILED,
                background_task_name=name,
                **{"exception.type": type(exc).__name__},
            )
            raise
        finally:
            exit_request_scope(token)

    return asyncio.create_task(runner(), name=name)


def _str_or_none(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["LogContextScope", "run_with_log_context"]
