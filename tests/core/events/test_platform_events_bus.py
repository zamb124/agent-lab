"""Единая шина событий платформы: publish → tail/group consumers (реальный Redis)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from apps.crm.services import crm_entity_events as _crm_entity_events
from core.config import get_settings
from core.events import (
    PLATFORM_EVENT_CATALOG_KEY,
    EventDelivery,
    PlatformEvent,
    PlatformEventCatalogEntry,
    PlatformEventGroupConsumer,
    is_registered_platform_event,
    load_platform_event_catalog,
    load_platform_event_catalog_entry,
    publish_domain_event,
    publish_event_to_users,
    register_platform_event,
    store_registered_platform_events,
)
from core.events.redis_client import events_redis_client
from core.worktracker import events as _worktracker_events
from tests.fixtures.platform_events import initial_platform_events_cursor, platform_events_listener

_ = (_crm_entity_events, _worktracker_events)

class _ProbePayload(BaseModel):
    probe_id: str


def test_event_delivery_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError):
        _ = EventDelivery()
    with pytest.raises(ValidationError):
        _ = EventDelivery(user_ids=["u1"], company_id="c1")
    with pytest.raises(ValidationError):
        _ = EventDelivery(user_ids=[])
    assert EventDelivery(user_ids=["u1"]).user_ids == ["u1"]
    assert EventDelivery(company_id="c1").company_id == "c1"
    assert EventDelivery(broadcast=True).broadcast is True


def test_empty_stream_cursor_is_not_dollar() -> None:
    assert initial_platform_events_cursor(None) == "0-0"
    assert initial_platform_events_cursor("1710000000000-0") == "1710000000000-0"


def test_ws_frame_excludes_delivery() -> None:
    event = PlatformEvent(
        type="notify/test/system_received",
        company_id="c1",
        payload={"title": "x"},
        delivery=EventDelivery(user_ids=["u1"]),
    )
    frame = event.ws_frame_json()
    assert '"delivery"' not in frame
    assert '"notify/test/system_received"' in frame


@pytest.mark.asyncio
async def test_publish_to_users_delivers_one_stream_entry(unique_id: str) -> None:
    """Одно событие с несколькими получателями — одна запись стрима."""
    event_type = "notify/test/system_received"
    marker = f"bus-{unique_id}"
    async with platform_events_listener() as receive:
        await publish_event_to_users(
            [f"u1_{unique_id}", f"u2_{unique_id}"],
            event_type,
            {"marker": marker},
            company_id="system",
        )
        events = await receive(event_type, f"u2_{unique_id}", 3.0)
        matched = [e for e in events if e["payload"].get("marker") == marker]
        assert len(matched) == 1
        assert matched[0]["delivery"]["user_ids"] == [f"u1_{unique_id}", f"u2_{unique_id}"]
        assert matched[0]["company_id"] == "system"


@pytest.mark.asyncio
async def test_domain_event_has_no_delivery(unique_id: str) -> None:
    marker = f"domain-{unique_id}"
    async with platform_events_listener() as receive:
        await publish_domain_event(
            "crm/entity/created",
            {"entity_id": marker},
            company_id="system",
            actor_user_id=f"actor_{unique_id}",
        )
        events = await receive("crm/entity/created", None, 3.0)
        matched = [e for e in events if e["payload"].get("entity_id") == marker]
        assert len(matched) == 1
        assert matched[0].get("delivery") is None
        assert matched[0]["meta"]["actor_user_id"] == f"actor_{unique_id}"


@pytest.mark.asyncio
async def test_group_consumer_receives_and_acks(unique_id: str) -> None:
    """Consumer group получает событие at-least-once и ACK'ает его."""
    received: list[PlatformEvent] = []
    done = asyncio.Event()
    marker = f"group-{unique_id}"

    async def _on_event(event: PlatformEvent) -> None:
        payload = event.payload
        if isinstance(payload, dict) and payload.get("marker") == marker:
            received.append(event)
            done.set()

    settings = get_settings()
    consumer = PlatformEventGroupConsumer(
        group=f"test_group_{unique_id}",
        consumer_name=f"consumer_{unique_id}",
        on_event=_on_event,
        redis_url=settings.database.redis_url,
    )
    consumer_task = asyncio.create_task(consumer.run())
    try:
        # дождаться создания группы (иначе событие уйдёт до XGROUP CREATE $)
        await asyncio.sleep(0.5)
        await publish_domain_event(
            "worktracker/work_item/assigned",
            {"marker": marker},
            company_id="system",
        )
        await asyncio.wait_for(done.wait(), timeout=10.0)
    finally:
        _ = consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    assert len(received) == 1
    assert received[0].type == "worktracker/work_item/assigned"


@pytest.mark.asyncio
async def test_catalog_register_store_and_load(unique_id: str) -> None:
    event_type = f"test/probe_{unique_id.replace('-', '_').lower()}/created"
    register_platform_event(event_type, _ProbePayload, description="Тестовое событие каталога.")
    assert is_registered_platform_event(event_type)
    # повторная регистрация той же модели idempotent
    register_platform_event(event_type, _ProbePayload, description="Тестовое событие каталога.")

    class _OtherPayload(BaseModel):
        other: str

    with pytest.raises(ValueError, match="already registered"):
        register_platform_event(event_type, _OtherPayload, description="Конфликт.")

    await store_registered_platform_events()
    catalog = await load_platform_event_catalog()
    entry = next((item for item in catalog if item.event_type == event_type), None)
    assert entry is not None
    assert "probe_id" in entry.payload_schema.get("properties", {})
    assert any(field.path == "probe_id" for field in entry.filter_fields)


@pytest.mark.asyncio
async def test_load_platform_event_catalog_entry_heals_and_none(unique_id: str) -> None:
    event_type = f"test/entry_{unique_id.replace('-', '_').lower()}/created"

    class EntryPayload(BaseModel):
        entry_id: str

    schema = EntryPayload.model_json_schema()
    stale = PlatformEventCatalogEntry(
        event_type=event_type,
        description="stale entry",
        payload_schema=schema,
        filter_fields=[],
    )
    redis = events_redis_client()
    _ = await redis.hset(
        PLATFORM_EVENT_CATALOG_KEY, mapping={event_type: stale.model_dump_json()}
    )

    healed = await load_platform_event_catalog_entry(event_type)
    assert healed is not None
    assert any(field.path == "entry_id" for field in healed.filter_fields)

    missing = await load_platform_event_catalog_entry(
        f"test/missing_{unique_id.replace('-', '_').lower()}/gone"
    )
    assert missing is None
