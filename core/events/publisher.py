"""
Publisher единой шины событий платформы.

Единственный способ опубликовать событие из любого процесса (HTTP-сервис,
TaskIQ worker): XADD в Redis Stream ``platform:events`` с approximate
MAXLEN-трим по ``settings.events.stream_maxlen``.

Очень тонкий слой — никакой бизнес-логики. Бизнес-логика обязана сама
формировать корректный ``PlatformEvent`` с типом из ``CoreFrontendEventTypes`` или
сервисного реестра (`core/events/catalog.py` + `apps/<svc>/.../events.py`).

Событие наследует ``trace_id`` и ``request_id`` от текущего
запроса-инициатора (HTTP/WS/TaskIQ), а ``company_id`` — от активной компании
контекста, если они не заданы явно. Redis недоступен — публикация падает
(Zero-Guess: событие не может быть потеряно молча).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, cast

from core.config import get_settings
from core.context import get_context
from core.events.contract import (
    PLATFORM_EVENTS_STREAM,
    SYSTEM_COMPANY_ID,
    EventDelivery,
    PlatformEvent,
    PlatformEventMeta,
)
from core.events.redis_client import close_events_redis_client, events_redis_client
from core.events.registry import assert_publishable_platform_event_type
from core.logging import get_log_context, get_logger
from core.types import JsonValue

logger = get_logger(__name__)


class _RedisXAddCommand(Protocol):
    def __call__(
        self,
        name: str,
        fields: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> Awaitable[str]: ...


async def close_publisher_client() -> None:
    """Закрыть Redis-клиент шины процесса (shutdown / тесты)."""
    await close_events_redis_client()


def _resolve_trace_id() -> str | None:
    """Берём trace_id из текущего бизнес-контекста или из лог-контекста."""
    context = get_context()
    if context is not None and context.trace_id:
        return context.trace_id
    log_ctx_trace = get_log_context().get("trace_id")
    if isinstance(log_ctx_trace, str) and log_ctx_trace:
        return log_ctx_trace
    return None


def _resolve_request_id() -> str | None:
    """Берём request_id из лог-контекста (бизнес Context его не несёт)."""
    log_ctx_request = get_log_context().get("request_id")
    if isinstance(log_ctx_request, str) and log_ctx_request:
        return log_ctx_request
    return None


def _resolve_company_id() -> str:
    """Активная компания контекста; вне company-контекста — system."""
    context = get_context()
    if context is not None and context.active_company is not None:
        return context.active_company.company_id
    return SYSTEM_COMPANY_ID


async def publish_event(event: PlatformEvent) -> None:
    """Опубликовать событие в Redis Stream `platform:events`."""
    _ = assert_publishable_platform_event_type(event.type)
    if not event.meta.trace_id:
        trace_id = _resolve_trace_id()
        if trace_id:
            event.meta.trace_id = trace_id
    if not event.meta.request_id:
        request_id = _resolve_request_id()
        if request_id:
            event.meta.request_id = request_id

    settings = get_settings()
    client = events_redis_client()
    xadd = cast(_RedisXAddCommand, client.xadd)
    _ = await xadd(
        PLATFORM_EVENTS_STREAM,
        {"event": event.model_dump_json()},
        maxlen=settings.events.stream_maxlen,
        approximate=True,
    )
    logger.debug(
        "platform_event.published",
        event_type=event.type,
        event_id=event.event_id,
        company_id=event.company_id,
        trace_id=event.meta.trace_id,
        platform_event_request_id=event.meta.request_id,
        delivery=event.delivery.model_dump(exclude_none=True) if event.delivery else None,
    )


async def publish_event_to_user(
    user_id: str,
    type: str,
    payload: JsonValue = None,
    *,
    company_id: str | None = None,
    actor_user_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Событие с UI-доставкой в сокеты конкретного пользователя."""
    await publish_event_to_users(
        [user_id],
        type,
        payload,
        company_id=company_id,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        trace_id=trace_id,
        request_id=request_id,
    )


async def publish_event_to_users(
    user_ids: list[str],
    type: str,
    payload: JsonValue = None,
    *,
    company_id: str | None = None,
    actor_user_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Одно событие с UI-доставкой перечисленным пользователям."""
    event = PlatformEvent(
        type=type,
        company_id=company_id if company_id is not None else _resolve_company_id(),
        payload=payload,
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id or _resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
        delivery=EventDelivery(user_ids=user_ids),
    )
    await publish_event(event)


async def publish_event_to_company(
    company_id: str,
    type: str,
    payload: JsonValue = None,
    *,
    actor_user_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Событие с UI-доставкой во все сокеты компании."""
    event = PlatformEvent(
        type=type,
        company_id=company_id,
        payload=payload,
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id or _resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
        delivery=EventDelivery(company_id=company_id),
    )
    await publish_event(event)


async def publish_event_broadcast(
    type: str,
    payload: JsonValue = None,
    *,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Платформенное событие с UI-доставкой во все подключённые сокеты."""
    event = PlatformEvent(
        type=type,
        company_id=SYSTEM_COMPANY_ID,
        payload=payload,
        meta=PlatformEventMeta(
            source="system",
            correlation_id=correlation_id,
            trace_id=_resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
        delivery=EventDelivery(broadcast=True),
    )
    await publish_event(event)


async def publish_domain_event(
    type: str,
    payload: JsonValue,
    *,
    company_id: str | None = None,
    actor_user_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    """Чисто доменное событие без UI-доставки (`delivery=None`)."""
    event = PlatformEvent(
        type=type,
        company_id=company_id if company_id is not None else _resolve_company_id(),
        payload=payload,
        meta=PlatformEventMeta(
            source="system",
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=_resolve_trace_id(),
            request_id=_resolve_request_id(),
        ),
        delivery=None,
    )
    await publish_event(event)
