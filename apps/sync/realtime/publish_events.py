"""Публикация realtime-событий Sync через `platform:ui_events`.

Вместо собственного Redis-канала используем платформенный единый поток
push-событий: бэкенд кладёт `UIEvent` в Redis-канал
`platform:ui_events`, а `core.websocket.manager` форвардит его в подключённые
сокеты `/sync/api/ws/notifications` (см. `architecture.mdc`, раздел
«REST-зеркало команд»). Один транспорт push'ей на всю платформу.

Адресация:
  - `recipient_user_ids: list[str]` -> много `publish_ui_event_to_user`.
  - `recipient_user_ids is None` -> `publish_ui_event_to_company` (broadcast
    в активные сокеты компании).

`channel_id` из `RealtimeEvent` мерджится в payload (если ещё нет),
чтобы клиент имел его без дополнительных полей конверта.
"""

from __future__ import annotations

from apps.sync.realtime.events import RealtimeEvent
from core.ui_events.dispatcher import publish_ui_event_to_company, publish_ui_event_to_user


async def publish_realtime_events(events: list[RealtimeEvent]) -> None:
    if not events:
        return
    for event in events:
        payload = dict(event.payload)
        if event.channel_id is not None and "channel_id" not in payload:
            payload["channel_id"] = event.channel_id
        if event.recipient_user_ids is None:
            await publish_ui_event_to_company(
                company_id=event.company_id,
                type=event.type,
                payload=payload,
            )
        else:
            for user_id in event.recipient_user_ids:
                await publish_ui_event_to_user(
                    user_id=user_id,
                    type=event.type,
                    payload=payload,
                )
