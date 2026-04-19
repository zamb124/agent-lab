"""
Publisher UI-событий через Redis Pub/Sub.

WebSocket-менеджер (`core/websocket/manager.py`) подписан на канал
`UI_EVENTS_REDIS_CHANNEL`, парсит конверт и форвардит UIEvent в сокеты
адресата (по target).

Очень тонкий слой — никакой бизнес-логики. Бизнес-логика обязана сама
формировать корректный UIEvent с типом из CoreUIEventTypes или сервисного
реестра (`apps/<svc>/.../ui_events.py`).
"""

from __future__ import annotations

import json
from typing import Optional

from core.logging import get_logger
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


async def publish_ui_event(event: UIEvent, target: UIEventTarget) -> None:
    """Опубликовать UIEvent в Redis Pub/Sub. Менеджер WS форвардит в сокеты."""
    from core.websocket.manager import notification_manager  # local import: цикл

    payload = _envelope(event, target)
    await notification_manager.publish_ui_envelope(payload)
    logger.debug(
        "UIEvent published: type=%s target=%s id=%s",
        event.type,
        target.model_dump(exclude_none=True),
        event.id,
    )


async def publish_ui_event_to_user(
    user_id: str,
    type: str,
    payload: object = None,
    *,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    """Шорткат: опубликовать UIEvent адресно одному пользователю."""
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(
            source="system",
            correlation_id=correlation_id,
            causation_id=causation_id,
            trace_id=trace_id,
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
) -> None:
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(
            source="system",
            correlation_id=correlation_id,
            trace_id=trace_id,
        ),
    )
    await publish_ui_event(event, UIEventTarget(company_id=company_id))


async def publish_ui_event_broadcast(
    type: str,
    payload: object = None,
    *,
    correlation_id: Optional[str] = None,
) -> None:
    event = UIEvent(
        type=type,
        payload=payload,
        meta=UIEventMeta(source="system", correlation_id=correlation_id),
    )
    await publish_ui_event(event, UIEventTarget(broadcast=True))
