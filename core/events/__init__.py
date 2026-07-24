"""
Единая шина событий платформы: Redis Stream ``platform:events``.

Бэкенд публикует событие через `publish_event(...)` (и хелперы
`publish_event_to_user/_to_company/_broadcast`, `publish_domain_event`).
Потребители:

- WebSocket-менеджер (tail): форвардит события с ``delivery`` в подключённые
  сокеты адресата, фронт диспатчит их в свой EventBus как обычные события.
- Consumer groups (durable, at-least-once): любой сервис перехватывает любое
  событие платформы — первый потребитель flows (триггеры `platform_event`
  и inbox flow-сотрудников).

Никаких отдельных «команд» / RPC — только события. «Нажать кнопку из бэка» =
бэк публикует событие, на которое подписан UI-компонент.
"""

from core.events.catalog import (
    PLATFORM_EVENT_CATALOG_KEY,
    load_platform_event_catalog,
    load_platform_event_catalog_entry,
    store_registered_platform_events,
)
from core.events.consumer import (
    PlatformEventGroupConsumer,
    PlatformEventHandler,
    PlatformEventTailReader,
)
from core.events.contract import (
    PLATFORM_EVENTS_STREAM,
    SYSTEM_COMPANY_ID,
    CoreFrontendEventTypes,
    EventDelivery,
    PlatformEvent,
    PlatformEventMeta,
    assert_platform_event_type,
)
from core.events.payload_filter_fields import (
    PlatformEventFilterField,
    derive_filter_fields,
    filter_field_by_path,
    validate_event_filters_against_fields,
)
from core.events.publisher import (
    close_publisher_client,
    publish_domain_event,
    publish_event,
    publish_event_broadcast,
    publish_event_to_company,
    publish_event_to_user,
    publish_event_to_users,
)
from core.events.redis_client import events_redis_client
from core.events.registry import (
    PlatformEventCatalogEntry,
    assert_publishable_platform_event_type,
    catalog_entry_for_event_type,
    is_dynamic_notify_event_type,
    is_registered_platform_event,
    platform_event_catalog,
    platform_event_payload_model,
    register_platform_event,
    registered_platform_event_types,
)

__all__ = [
    "PLATFORM_EVENTS_STREAM",
    "PLATFORM_EVENT_CATALOG_KEY",
    "SYSTEM_COMPANY_ID",
    "CoreFrontendEventTypes",
    "EventDelivery",
    "PlatformEvent",
    "PlatformEventCatalogEntry",
    "PlatformEventFilterField",
    "PlatformEventGroupConsumer",
    "PlatformEventHandler",
    "PlatformEventMeta",
    "PlatformEventTailReader",
    "assert_platform_event_type",
    "assert_publishable_platform_event_type",
    "catalog_entry_for_event_type",
    "close_publisher_client",
    "derive_filter_fields",
    "events_redis_client",
    "filter_field_by_path",
    "is_dynamic_notify_event_type",
    "is_registered_platform_event",
    "load_platform_event_catalog",
    "load_platform_event_catalog_entry",
    "platform_event_catalog",
    "platform_event_payload_model",
    "publish_domain_event",
    "publish_event",
    "publish_event_broadcast",
    "publish_event_to_company",
    "publish_event_to_user",
    "publish_event_to_users",
    "register_platform_event",
    "registered_platform_event_types",
    "store_registered_platform_events",
    "validate_event_filters_against_fields",
]
