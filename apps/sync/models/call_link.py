"""Гостевая ссылка на звонок Sync."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.sync.models.channel_member import SyncChannelMember
from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncCallLink(PlatformModel):
    """Строка ``sync_call_links``, алиас ``sync``, ``__global_model__``.

    ``channel_id`` ссылается на ``sync_channels.channel_id``, ON DELETE CASCADE.
    ``call_id`` ссылается на ``sync_calls`` (ещё SQLAlchemy), ON DELETE SET NULL.
    В ``0001`` эти внешние ключи остаются. Поиск по токену без компании — вход гостя.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_call_links"
        indexes: list[Index] = [
            Index(["channel_id"]),
            Index(["company_id"]),
            Index(["expires_at"]),
            Index(["calendar_event_id"]),
        ]

    link_token: str = DbField(db_pk=True, max_length=64)
    channel_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    created_by_user_id: str = DbField(max_length=64)
    expires_at: datetime
    call_id: str | None = DbField(default=None, max_length=64)
    call_type: str = DbField(default="video", max_length=8)
    created_at: datetime = DbField(default_factory=_utcnow)
    title: str | None = DbField(default=None, db_type="TEXT")
    scheduled_start_at: datetime | None = DbField(default=None)
    scheduled_end_at: datetime | None = DbField(default=None)
    calendar_event_id: str | None = DbField(default=None, max_length=64)
    is_persistent_channel_link: bool = DbField(default=False)

    @classmethod
    async def require_active_call_link(cls, link_token: str) -> SyncCallLink:
        row = await cls.objects.filter(link_token=link_token).get_or_none()
        if row is None:
            raise ValueError(f"Link {link_token} not found.")
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise ValueError("Link expired.")
        return row

    @classmethod
    async def require_company_call_link(
        cls,
        link_token: str,
        company_id: str,
    ) -> SyncCallLink:
        row = await cls.objects.filter(
            link_token=link_token, company_id=company_id
        ).get_or_none()
        if row is None:
            raise ValueError(f"Link {link_token} not found.")
        return row

    @classmethod
    async def delete_in_company(cls, company_id: str, link_token: str) -> bool:
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if link_token == "":
            raise ValueError("link_token cannot be empty.")
        deleted = await cls.objects.filter(
            link_token=link_token, company_id=company_id
        ).delete()
        return deleted > 0

    @classmethod
    async def update_calendar_call_link(
        cls,
        link_token: str,
        company_id: str,
        *,
        title: str | None,
        scheduled_start_at: datetime,
        scheduled_end_at: datetime,
        expires_at: datetime,
    ) -> None:
        row = await cls.require_company_call_link(link_token, company_id)
        if row.calendar_event_id is None:
            raise ValueError("Link is not bound to a calendar event.")
        _ = await cls.objects.filter(
            link_token=link_token, company_id=company_id
        ).update(
            using="sync",
            title=title,
            scheduled_start_at=scheduled_start_at,
            scheduled_end_at=scheduled_end_at,
            expires_at=expires_at,
        )

    @classmethod
    async def list_unordered_scheduled_calendar_links_for_user(
        cls,
        company_id: str,
        user_id: str,
        *,
        range_start: datetime,
        range_end: datetime,
        channel_id: str | None,
    ) -> list[Self]:
        """Календарные ссылки каналов, где пользователь участник, пересекающие [range_start, range_end) по строгому неравенству. channel_id None — все такие каналы. Чужой channel_id и пустое членство — []. Порядка и limit нет."""
        member_rows = await SyncChannelMember.objects.filter(
            company_id=company_id,
            user_id=user_id,
        ).all()
        member_channel_ids = [row.channel_id for row in member_rows]
        if channel_id is not None:
            if channel_id not in member_channel_ids:
                return []
            member_channel_ids = [channel_id]
        if len(member_channel_ids) == 0:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            channel_id__in=member_channel_ids,
            calendar_event_id__isnull=False,
            scheduled_start_at__isnull=False,
            scheduled_end_at__isnull=False,
            scheduled_start_at__lt=range_end,
            scheduled_end_at__gt=range_start,
        ).all()

    @classmethod
    async def find_by_calendar_event(
        cls, company_id: str, calendar_event_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            calendar_event_id=calendar_event_id,
        ).get_or_none()

    @classmethod
    async def find_persistent_for_channel(
        cls, company_id: str, channel_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            channel_id=channel_id,
            is_persistent_channel_link=True,
        ).get_or_none()

    @classmethod
    async def update_expires_at_by_link_token(cls, link_token: str, expires_at: datetime) -> None:
        """Пишет expires_at по PK link_token. Нет строки — ничего не меняет."""
        _ = await cls.objects.filter(link_token=link_token).update(
            using="sync", expires_at=expires_at
        )

    @classmethod
    async def attach_call(cls, link_token: str, call_id: str) -> None:
        _ = await cls.objects.filter(link_token=link_token).update(
            using="sync", call_id=call_id
        )
