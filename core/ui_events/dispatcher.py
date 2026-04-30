"""
Publisher UI-событий через Redis Pub/Sub.

WebSocket-менеджер (`core/websocket/manager.py`) подписан на канал
`UI_EVENTS_REDIS_CHANNEL`, парсит конверт и форвардит UIEvent в сокеты
адресата (по target).

Очень тонкий слой — никакой бизнес-логики. Бизнес-логика обязана сама
формировать корректный UIEvent с типом из CoreUIEventTypes или сервисного
реестра (`apps/<svc>/.../ui_events.py`).

UI-событие наследует ``trace_id`` и ``request_id`` от текущего
запроса-инициатора (HTTP/WS/TaskIQ) — оба поля проставляются
автоматически в ``UIEvent.meta``, чтобы поиск по request_id в логах
охватывал и сам запрос, и порождённые им push-события.
"""

from __future__ import annotations

import json
from typing import Optional

from core.context import get_context
from core.logging import get_log_context, get_logger
from core.ui_events.contract import UIEvent, UIEventMeta, UIEventTarget

logger = get_logger(__name__)

UI_EVENTS_REDIS_CHANNEL = "platform:ui_events"


def _envelope(event: UIEvent, target: UIEventTarget) -> str:
    target.assert_valid()
    return json.dumps(
        {
            "target": target.model_dump(mode="json"),
            "event": event.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )


def _resolve_trace_id() -> Optional[str]:
    """Берём trace_id из текущего бизнес-контекста или из лог-контекста."""
    context = get_context()
    if context is not None and getattr(context, "trace_id", None):
        return context.trace_id
    log_ctx_trace = get_log_context().get("trace_id")
    if isinstance(log_ctx_trace, str) and log_ctx_trace:
        return log_ctx_trace
    return None


def _resolve_request_id() -> Optional[str]:
    """Берём request_id из лог-контекста (бизнес Context его не несёт)."""
    log_ctx_request = get_log_context().get("request_id")
    if isinstance(log_ctx_request, str) and log_ctx_request:
        return log_ctx_request
    return None


async def publish_ui_event(event: UIEvent, target: UIEventTarget) -> None:
    """Опубликовать UIEvent в Redis Pub/Sub. Менеджер WS форвардит в сокеты."""
    from core.websocket.manager import notification_manager  # local import: цикл

    if event.meta and not event.meta.trace_id:
        trace_id = _resolve_trace_id()
        if trace_id:
            event.meta.trace_id = trace_id
    if event.meta and not event.meta.request_id:
        request_id = _resolve_request_id()
        if request_id:
            event.meta.request_id = request_id

    payload = _envelope(event, target)
    await notification_manager.publish_ui_envelope(payload)
    logger.debug(
        "ui_event.published",
        event_type=event.type,
        event_id=event.id,
        trace_id=event.meta.trace_id if event.meta else None,
        ui_event_request_id=event.meta.request_id if event.meta else None,
        target=target.model_dump(exclude_none=True),
    )


async def publish_ui_event_to_user(
    user_id: str,
    type: str,
    payload: object = None,
    *,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(
            source="system",
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id or _resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
    )
    await publish_ui_event(event, UIEventTarget(user_id=user_id))


async def publish_ui_event_to_company(
    company_id: str,
    type: str,
    payload: object = None,
    *,
    correlation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(
            source="system",
            correlation_id=correlation_id,
            trace_id=trace_id or _resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
    )
    await publish_ui_event(event, UIEventTarget(company_id=company_id))


async def publish_ui_event_broadcast(
    type: str,
    payload: object = None,
    *,
    correlation_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(
            source="system",
            correlation_id=correlation_id,
            trace_id=_resolve_trace_id(),
            request_id=request_id or _resolve_request_id(),
        ),
    )
    await publish_ui_event(event, UIEventTarget(broadcast=True))
