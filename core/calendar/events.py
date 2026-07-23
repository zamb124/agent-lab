"""Каталог событий календаря на шине `platform:events`."""

from __future__ import annotations

from pydantic import BaseModel

from core.events import register_platform_event

CALENDAR_EVENT_CREATED = "calendar/event/created"


class CalendarEventCreatedPayload(BaseModel):
    event_id: str
    company_id: str
    start_at: str | None = None
    end_at: str | None = None
    timezone: str | None = None
    title: str | None = None
    provider: str | None = None


register_platform_event(
    CALENDAR_EVENT_CREATED,
    CalendarEventCreatedPayload,
    description="Создано / получено приглашение на событие календаря.",
)
