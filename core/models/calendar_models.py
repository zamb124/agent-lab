"""
Модели календаря платформы.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from core.models.base import StrictBaseModel


class CalendarProvider(StrEnum):
    PLATFORM = "platform"
    GOOGLE = "google"
    YANDEX = "yandex"


class CalendarEventSource(StrEnum):
    PLATFORM = "platform"
    CRM = "crm"
    SYNC = "sync"
    FLOWS = "flows"
    GOOGLE = "google"
    YANDEX = "yandex"


class CalendarEventStatus(StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class CalendarAttendee(StrictBaseModel):
    attendee_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    response_status: str = Field(default="needsAction")


class CalendarExternalRef(StrictBaseModel):
    provider: CalendarProvider
    calendar_id: str
    external_event_id: str
    etag: str | None = None
    last_synced_at: datetime | None = None


class CalendarEvent(StrictBaseModel):
    event_id: str
    source: CalendarEventSource
    source_id: str
    company_id: str
    namespace: str | None = None
    kind: str
    title: str
    description: str | None = None
    location: str | None = None
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    timezone: str
    all_day: bool = False
    start_at: datetime
    end_at: datetime
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    recurrence_rule: str | None = None
    recurrence_id: str | None = None
    series_id: str | None = None
    deep_link: str | None = None
    external_refs: list[CalendarExternalRef] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarEventUpsertPayload(StrictBaseModel):
    title: str
    kind: str = "event"
    source: CalendarEventSource = CalendarEventSource.PLATFORM
    source_id: str | None = None
    namespace: str | None = None
    description: str | None = None
    location: str | None = None
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    timezone: str = "UTC"
    all_day: bool = False
    start_at: datetime
    end_at: datetime
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    recurrence_rule: str | None = None
    recurrence_id: str | None = None
    series_id: str | None = None
    deep_link: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class CalendarIntegrationCredentials(StrictBaseModel):
    username: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None


class CalendarIntegrationSettings(StrictBaseModel):
    default_calendar_id: str | None = None
    sync_enabled: bool = True
    sync_inbound_enabled: bool = True
    sync_outbound_enabled: bool = True
    notifications_enabled: bool = True


class CalendarIntegration(StrictBaseModel):
    integration_id: str
    company_id: str
    user_id: str
    provider: CalendarProvider
    credentials: CalendarIntegrationCredentials
    settings: CalendarIntegrationSettings = Field(default_factory=CalendarIntegrationSettings)
    created_at: datetime
    updated_at: datetime


class CalendarIntegrationConnectPayload(StrictBaseModel):
    provider: CalendarProvider
    username: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None
    default_calendar_id: str | None = None
    sync_enabled: bool = True
    sync_inbound_enabled: bool = True
    sync_outbound_enabled: bool = True
    notifications_enabled: bool = True
