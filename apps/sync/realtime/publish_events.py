"""Публикация realtime-событий Sync через шину `platform:events`.

Вместо собственного Redis-канала используем единую шину событий платформы:
бэкенд публикует `PlatformEvent` в Redis Stream `platform:events`,
`core.websocket.manager` форвардит его в подключённые сокеты
`/sync/api/ws/notifications` (см. `architecture.mdc`, раздел
«REST-зеркало команд»), а durable-потребители (триггеры flows) читают те же
события at-least-once. Один транспорт событий на всю платформу.

Адресация:
  - `recipient_user_ids: list[str]` -> одно `publish_event_to_users`.
  - `recipient_user_ids is None` -> `publish_event_to_company` (broadcast
    в активные сокеты компании).

`channel_id` из `RealtimeEvent` мерджится в payload (если ещё нет),
чтобы клиент имел его без дополнительных полей конверта.
"""

from __future__ import annotations

from apps.sync.realtime.events import RealtimeEvent
from core.events import publish_event_to_company, publish_event_to_users


async def publish_realtime_events(events: list[RealtimeEvent]) -> None:
    if not events:
        return
    for event in events:
        payload = dict(event.payload)
        if event.channel_id is not None and "channel_id" not in payload:
            payload["channel_id"] = event.channel_id
        if event.recipient_user_ids is None:
            await publish_event_to_company(
                company_id=event.company_id,
                type=event.type,
                payload=payload,
            )
        else:
            await publish_event_to_users(
                event.recipient_user_ids,
                event.type,
                payload,
                company_id=event.company_id,
            )
