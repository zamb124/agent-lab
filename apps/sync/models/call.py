"""Звонок Sync."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.errors.boundary import PlatformNotFoundError
from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncCall(PlatformModel):
    """Строка ``sync_calls``, алиас ``sync``, ``__global_model__``.

    ``channel_id`` ссылается на ``sync_channels.channel_id``, ON DELETE CASCADE.
    В ``0001`` этот внешний ключ остаётся. Ответ API — ``CallRead``: там участники
    и закрытые ``mode``/``status``, которых нет колонками в том же виде.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_calls"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["channel_id"]),
            Index(["status"]),
        ]

    call_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    channel_id: str = DbField(max_length=64)
    mode: str = DbField(max_length=8)
    call_type: str = DbField(max_length=8)
    created_by_user_id: str = DbField(max_length=64)
    status: str = DbField(default="ringing", max_length=16)
    livekit_room_name: str | None = DbField(default=None, max_length=128)
    started_at: datetime | None = DbField(default=None)
    ended_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=_utcnow)

    @classmethod
    async def require_company_call(cls, call_id: str, company_id: str) -> SyncCall:
        row = await cls.objects.filter(
            call_id=call_id, company_id=company_id
        ).get_or_none()
        if row is None:
            raise PlatformNotFoundError(f"Call {call_id} not found", error_code="not_found")
        return row

    @classmethod
    async def mark_call_status(
        cls,
        call_id: str,
        status: str,
        *,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        query = cls.objects.filter(call_id=call_id)
        if started_at is not None and ended_at is not None:
            raise ValueError("call status patch sets both started_at and ended_at")
        if started_at is not None:
            _ = await query.update(using="sync", status=status, started_at=started_at)
            return
        if ended_at is not None:
            _ = await query.update(using="sync", status=status, ended_at=ended_at)
            return
        raise ValueError("call status patch requires started_at or ended_at")

    @classmethod
    async def assign_admin(cls, call_id: str, user_id: str) -> None:
        _ = await cls.objects.filter(call_id=call_id).update(
            using="sync", created_by_user_id=user_id
        )

    @classmethod
    async def find_open_in_channel(
        cls, company_id: str, channel_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            channel_id=channel_id,
            company_id=company_id,
            status__in=["ringing", "active"],
        ).get_or_none()
