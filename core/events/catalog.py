"""
Каталог типов событий платформы (Redis HASH + in-process registry).

Каждый сервис регистрирует типы через `register_platform_event` (см.
`core/events/registry.py`). На старте процесс публикует свои регистрации в
Redis HASH `platform:event_catalog`; полный каталог платформы читается через
`load_platform_event_catalog` (endpoint flows / UI триггеров).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, cast

from core.events.redis_client import events_redis_client
from core.events.registry import (
    PlatformEventCatalogEntry,
    is_dynamic_notify_event_type,
    is_registered_platform_event,
    platform_event_catalog,
    platform_event_payload_model,
    register_platform_event,
    registered_platform_event_types,
)
from core.logging import get_logger

logger = get_logger(__name__)

PLATFORM_EVENT_CATALOG_KEY = "platform:event_catalog"


class _RedisHSetCommand(Protocol):
    def __call__(self, name: str, mapping: dict[str, str]) -> Awaitable[int]: ...


class _RedisHGetAllCommand(Protocol):
    def __call__(self, name: str) -> Awaitable[dict[str, str]]: ...


async def store_registered_platform_events() -> None:
    """Опубликовать регистрации процесса в общий каталог (Redis HASH)."""
    entries = platform_event_catalog()
    if not entries:
        return
    mapping = {entry.event_type: entry.model_dump_json() for entry in entries}
    client = events_redis_client()
    hset = cast(_RedisHSetCommand, client.hset)
    _ = await hset(PLATFORM_EVENT_CATALOG_KEY, mapping=mapping)
    logger.info("platform_event.catalog_stored", entries=len(mapping))


async def load_platform_event_catalog() -> list[PlatformEventCatalogEntry]:
    """Полный каталог платформы из Redis (регистрации всех сервисов)."""
    client = events_redis_client()
    hgetall = cast(_RedisHGetAllCommand, client.hgetall)
    raw_entries = await hgetall(PLATFORM_EVENT_CATALOG_KEY)
    entries = [
        PlatformEventCatalogEntry.model_validate_json(raw_entry).with_ensured_filter_fields()
        for _event_type, raw_entry in sorted(raw_entries.items())
    ]
    return entries


async def load_platform_event_catalog_entry(
    event_type: str,
) -> PlatformEventCatalogEntry | None:
    """Одна запись каталога по типу; нет в Redis — None (после auto-heal filter_fields)."""
    catalog = await load_platform_event_catalog()
    for entry in catalog:
        if entry.event_type == event_type:
            return entry
    return None


__all__ = [
    "PLATFORM_EVENT_CATALOG_KEY",
    "PlatformEventCatalogEntry",
    "is_dynamic_notify_event_type",
    "is_registered_platform_event",
    "load_platform_event_catalog",
    "load_platform_event_catalog_entry",
    "platform_event_catalog",
    "platform_event_payload_model",
    "register_platform_event",
    "registered_platform_event_types",
    "store_registered_platform_events",
]
