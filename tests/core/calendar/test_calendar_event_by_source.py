"""Чтение CalendarEvent по (company_id, source, source_id)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.models.calendar_models import CalendarEvent, CalendarEventSource


@pytest.mark.asyncio
async def test_by_source_matches_full_key(unique_id: str) -> None:
    company_id = f"calco_{unique_id}"
    other_company_id = f"calco_other_{unique_id}"
    source_id = f"src_{unique_id}"
    start_at = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    event = CalendarEvent(
        event_id=f"evt_{unique_id}",
        company_id=company_id,
        source=CalendarEventSource.SYNC,
        source_id=source_id,
        kind="meeting",
        title="Lookup",
        timezone="UTC",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
    )
    _ = await CalendarEvent.set(event)

    found = await CalendarEvent.by_company_source_and_source_id(company_id, CalendarEventSource.SYNC, source_id)
    assert found is not None
    assert found.event_id == event.event_id
    assert await CalendarEvent.by_company_source_and_source_id(other_company_id, CalendarEventSource.SYNC, source_id) is None
    assert await CalendarEvent.by_company_source_and_source_id(company_id, CalendarEventSource.GOOGLE, source_id) is None
    assert await CalendarEvent.by_company_source_and_source_id(company_id, CalendarEventSource.SYNC, f"missing_{unique_id}") is None
    with pytest.raises(ValueError, match="source_id cannot be empty"):
        _ = await CalendarEvent.by_company_source_and_source_id(company_id, CalendarEventSource.SYNC, "")
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await CalendarEvent.by_company_source_and_source_id("", CalendarEventSource.SYNC, source_id)

    assert await CalendarEvent.delete_by_company_and_event(other_company_id, event.event_id) is False
    assert await CalendarEvent.delete_by_company_and_event(company_id, event.event_id) is True
    assert await CalendarEvent.delete_by_company_and_event(company_id, event.event_id) is False
    assert await CalendarEvent.get(event.event_id) is None
    with pytest.raises(ValueError, match="event_id cannot be empty"):
        _ = await CalendarEvent.delete_by_company_and_event(company_id, "")


@pytest.mark.asyncio
async def test_upsert_by_event_id_updates_same_row(unique_id: str) -> None:
    company_id = f"calup_{unique_id}"
    other_company_id = f"calup_other_{unique_id}"
    start_at = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    event = CalendarEvent(
        event_id=f"evt_{unique_id}",
        company_id=company_id,
        source=CalendarEventSource.SYNC,
        source_id=f"src_{unique_id}",
        kind="meeting",
        title="First",
        timezone="UTC",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
    )
    await CalendarEvent.merge_by_event_id(event)
    event.title = "Second"
    await CalendarEvent.merge_by_event_id(event)
    stored = await CalendarEvent.get(event.event_id)
    assert stored is not None
    assert stored.title == "Second"
    assert stored.company_id == company_id

    clash = event.model_copy(update={"event_id": f"evt_other_{unique_id}", "title": "Clash"})
    with pytest.raises(ValueError, match="already exists"):
        await CalendarEvent.merge_by_event_id(clash)

    foreign = event.model_copy(update={"company_id": other_company_id, "source_id": f"other_{unique_id}"})
    with pytest.raises(ValueError, match="another company"):
        await CalendarEvent.merge_by_event_id(foreign)
    with pytest.raises(ValueError, match="event_id cannot be empty"):
        await CalendarEvent.merge_by_event_id(event.model_copy(update={"event_id": ""}))
