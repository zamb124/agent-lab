"""
Модели календаря платформы.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

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
    attendee_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    response_status: str = Field(default="needsAction")


class CalendarExternalRef(StrictBaseModel):
    provider: CalendarProvider
    calendar_id: str
    external_event_id: str
    etag: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class CalendarEvent(StrictBaseModel):
    event_id: str
    source: CalendarEventSource
    source_id: str
    company_id: str
    namespace: Optional[str] = None
    kind: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    timezone: str
    all_day: bool = False
    start_at: datetime
    end_at: datetime
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    recurrence_rule: Optional[str] = None
    recurrence_id: Optional[str] = None
    series_id: Optional[str] = None
    deep_link: Optional[str] = None
    external_refs: list[CalendarExternalRef] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CalendarIntegrationCredentials(StrictBaseModel):
    username: Optional[str] = None
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None
    token_type: Optional[str] = None


class CalendarIntegrationSettings(StrictBaseModel):
    default_calendar_id: Optional[str] = None
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
