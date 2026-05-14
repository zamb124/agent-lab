"""
UI Events: единый канал событий backend → UI.

Бэкенд публикует событие через `publish_ui_event(...)` (Redis Pub/Sub),
WebSocket-менеджер форвардит его в подключённые сокеты адресата, фронт диспатчит
в свой EventBus как обычное событие. Подписанные на это имя компоненты реагируют.

Никаких отдельных «команд» / RPC — только события. «Нажать кнопку из бэка» =
бэк публикует событие, на которое подписан UI-компонент.
"""

from core.ui_events.contract import (
    CoreUIEventTypes,
    UIEvent,
    UIEventMeta,
    UIEventTarget,
    assert_ui_event_type,
)
from core.ui_events.dispatcher import (
    UI_EVENTS_REDIS_CHANNEL,
    publish_ui_event,
    publish_ui_event_broadcast,
    publish_ui_event_to_company,
    publish_ui_event_to_user,
)

__all__ = [
    "UIEvent",
    "UIEventMeta",
    "UIEventTarget",
    "CoreUIEventTypes",
    "assert_ui_event_type",
    "publish_ui_event",
    "publish_ui_event_to_user",
    "publish_ui_event_to_company",
    "publish_ui_event_broadcast",
    "UI_EVENTS_REDIS_CHANNEL",
]
