"""
Модели календаря платформы.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index, execute_raw
from pydantic import ConfigDict, Field

from core.models.base import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.types import require_json_object


class CalendarProvider(StrEnum):
    PLATFORM = "platform"
    GOOGLE = "google"
    YANDEX = "yandex"
    MAILRU = "mailru"
    CALDAV = "caldav"


class CalendarEventSource(StrEnum):
    PLATFORM = "platform"
    CRM = "crm"
    SYNC = "sync"
    FLOWS = "flows"
    GOOGLE = "google"
    YANDEX = "yandex"
    MAILRU = "mailru"
    CALDAV = "caldav"


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



def _calendar_required(value: str, field_name: str) -> str:
    if value == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value

class CalendarEvent(PlatformModel):
    """Событие календаря. Таблица ``calendar_events`` в ``platform_shared``.

    ``__global_model__``: напоминание о Sync-встрече читает все компании.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    event_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "calendar_events"
        indexes: list[Index] = [
            Index(("company_id", "source", "source_id"), unique=True),
            Index(("company_id", "start_at", "end_at")),
            Index(("company_id", "kind", "start_at")),
            Index(("attendees",), method="gin"),
            Index(("external_refs",), method="gin"),
            Index(("metadata",), method="gin"),
        ]

    source: CalendarEventSource = DbField(db_index=True, max_length=64)
    source_id: str = DbField(max_length=255)
    company_id: str = DbField(db_index=True, max_length=255)
    namespace: str | None = DbField(default=None, db_index=True, max_length=255)
    kind: str = DbField(db_index=True, max_length=64)
    title: str = DbField(max_length=1024)
    description: str | None = DbField(default=None, db_type="TEXT")
    location: str | None = DbField(default=None, max_length=1024)
    status: CalendarEventStatus = DbField(default=CalendarEventStatus.CONFIRMED, db_index=True, max_length=32)
    timezone: str = DbField(max_length=64)
    all_day: bool = DbField(default=False)
    start_at: datetime = DbField(db_index=True)
    end_at: datetime = DbField(db_index=True)
    attendees: list[CalendarAttendee] = DbField(default_factory=list, db_type="JSONB")
    recurrence_rule: str | None = DbField(default=None, db_type="TEXT")
    recurrence_id: str | None = DbField(default=None, db_index=True, max_length=255)
    series_id: str | None = DbField(default=None, db_index=True, max_length=255)
    deep_link: str | None = DbField(default=None, db_type="TEXT")
    external_refs: list[CalendarExternalRef] = DbField(default_factory=list, db_type="JSONB")
    metadata: dict[str, str] = DbField(default_factory=dict, db_type="JSONB")
    mailbox_binding_id: str | None = DbField(default=None, db_index=True, max_length=255)
    created_by_user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    updated_by_user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.event_id == "" or self.company_id == "" or self.source_id == "" or self.title == "":
            raise ValueError("event_id, company_id, source_id and title are required")
        if self.timezone == "":
            raise ValueError("timezone cannot be empty.")
        self.updated_at = datetime.now(timezone.utc)


    @classmethod
    async def by_event_id(cls, company_id: str, event_id: str) -> Self | None:
        """Строка компании по event_id. Нет строки — None. Пустые company_id и event_id — ValueError."""
        return await cls.objects.filter(
            event_id=_calendar_required(event_id, "event_id"),
            company_id=_calendar_required(company_id, "company_id"),
        ).get_or_none()

    @classmethod
    async def by_company_source_and_source_id(
        cls, company_id: str, source: str, source_id: str
    ) -> Self | None:
        """Уникальный ключ company_id, source, source_id. Нет строки — None."""
        return await cls.objects.filter(
            company_id=_calendar_required(company_id, "company_id"),
            source=CalendarEventSource(source),
            source_id=_calendar_required(source_id, "source_id"),
        ).get_or_none()

    @classmethod
    async def merge_by_event_id(cls, event: Self) -> None:
        """Слияние по event_id. Возвращает None. Тот же source и source_id с другим event_id — ValueError. event_id другой компании — ValueError."""
        event_id = _calendar_required(event.event_id, "event_id")
        clash = await cls.by_company_source_and_source_id(event.company_id, event.source, event.source_id)
        if clash is not None and clash.event_id != event_id:
            raise ValueError("calendar event already exists for this company, source and source_id")
        existing = await cls.objects.filter(event_id=event_id).get_or_none()
        if existing is None:
            _ = await cls.objects.create(instance=event)
            return
        if existing.company_id != event.company_id:
            raise ValueError("event_id belongs to another company")
        _ = await event.save()

    @classmethod
    async def delete_by_company_and_event(cls, company_id: str, event_id: str) -> bool:
        """Удаление события компании. Нет строки — False."""
        deleted = await cls.objects.filter(
            event_id=_calendar_required(event_id, "event_id"),
            company_id=_calendar_required(company_id, "company_id"),
        ).delete()
        return deleted > 0

    @classmethod
    async def list_overlapping_by_start_at_asc(
        cls, company_id: str, start_at: datetime, end_at: datetime, limit: int
    ) -> list[Self]:
        """События, пересекающие окно, ORDER BY start_at ASC, не больше limit. Пустой company_id — ValueError company_id cannot be empty. limit в теле не проверяется."""
        return await cls.objects.filter(
            company_id=_calendar_required(company_id, "company_id"),
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).order_by("start_at").limit(limit).all()

    @classmethod
    async def list_unsent_platform_meeting_reminders_by_start_at_asc(
        cls,
        *,
        window_start: datetime,
        window_end: datetime,
        limit: int,
    ) -> list[Self]:
        """События платформы в полуинтервале start_at, с sync_link_token, sync_meeting = 1 и без sync_join_reminder_sent_at. ORDER BY start_at ASC, не больше limit. limit в теле не проверяется."""
        rows = await execute_raw(
            """
            SELECT event_id, company_id, source, source_id, namespace, kind, title,
                   description, location, status, timezone, all_day, start_at, end_at,
                   attendees, recurrence_rule, recurrence_id, series_id, deep_link,
                   external_refs, metadata, mailbox_binding_id, created_by_user_id,
                   updated_by_user_id, created_at, updated_at
            FROM calendar_events
            WHERE source = $1
              AND start_at >= $2
              AND start_at < $3
              AND metadata->>'sync_link_token' IS NOT NULL
              AND metadata->>'sync_meeting' = '1'
              AND metadata->>'sync_join_reminder_sent_at' IS NULL
            ORDER BY start_at ASC
            LIMIT $4
            """,
            [CalendarEventSource.PLATFORM.value, window_start, window_end, limit],
            using="shared",
        )
        return [
            cls.model_validate(require_json_object(row, "calendar_events"))
            for row in rows
        ]



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
    mailbox_binding_id: str | None = None


class CalendarIntegrationCredentials(StrictBaseModel):
    username: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None


class CalendarIntegrationSettings(StrictBaseModel):
    default_calendar_id: str | None = None
    caldav_base_url: str | None = None
    sync_enabled: bool = True
    sync_inbound_enabled: bool = True
    sync_outbound_enabled: bool = True
    notifications_enabled: bool = True


class CalendarIntegrationCredentialMetadata(StrictBaseModel):
    username: str | None = None
    calendar_settings: CalendarIntegrationSettings = Field(default_factory=CalendarIntegrationSettings)


class CalendarIntegration(StrictBaseModel):
    integration_id: str
    company_id: str
    user_id: str
    provider: CalendarProvider
    mailbox_binding_id: str | None = None
    credentials: CalendarIntegrationCredentials = Field(exclude=True)
    settings: CalendarIntegrationSettings = Field(default_factory=CalendarIntegrationSettings)
    created_at: datetime
    updated_at: datetime


class CalendarAutolinkStatus(StrEnum):
    """
    Итог авто-подъёма календаря для почтового ящика. Хранится на MailboxBinding,
    возвращается календарём в CalendarAutolinkOutcome.
    """

    LINKED = "linked"
    UNSUPPORTED = "unsupported"
    NEEDS_OAUTH = "needs_oauth"
    NEEDS_PASSWORD = "needs_password"
    FAILED = "failed"
    DISABLED = "disabled"


class CalendarAutolinkOutcome(StrictBaseModel):
    status: CalendarAutolinkStatus
    provider: CalendarProvider | None = None
    integration_id: str | None = None
    detail: str


class CalendarIntegrationConnectPayload(StrictBaseModel):
    provider: CalendarProvider
    mailbox_binding_id: str | None = None
    username: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None
    default_calendar_id: str | None = None
    caldav_base_url: str | None = None
    sync_enabled: bool = True
    sync_inbound_enabled: bool = True
    sync_outbound_enabled: bool = True
    notifications_enabled: bool = True
