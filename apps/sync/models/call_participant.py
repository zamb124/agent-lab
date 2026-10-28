"""Участник звонка Sync."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


class SyncCallParticipant(PlatformModel):
    """Строка ``sync_call_participants``, алиас ``sync``, ``__global_model__``.

    ``call_id`` ссылается на ``sync_calls``, ON DELETE CASCADE.
    Уникальность пары ``(call_id, user_id)``. В ответе звонка участник — ``CallParticipantRead``.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_call_participants"
        indexes: list[Index] = [
            Index(["call_id"]),
            Index(["user_id"]),
        ]
        unique_together: list[tuple[str, str]] = [("call_id", "user_id")]

    call_participant_id: str = DbField(db_pk=True, max_length=64)
    call_id: str = DbField(max_length=64)
    user_id: str = DbField(max_length=64)
    status: str = DbField(default="invited", max_length=16)
    joined_at: datetime | None = DbField(default=None)
    left_at: datetime | None = DbField(default=None)

    @classmethod
    async def mark_call_participant_status(
        cls,
        call_id: str,
        user_id: str,
        status: str,
        *,
        joined_at: datetime | None = None,
        left_at: datetime | None = None,
    ) -> None:
        query = cls.objects.filter(call_id=call_id, user_id=user_id)
        if joined_at is not None and left_at is not None:
            raise ValueError("participant status patch sets both joined_at and left_at")
        if joined_at is not None:
            _ = await query.update(using="sync", status=status, joined_at=joined_at)
            return
        if left_at is not None:
            _ = await query.update(using="sync", status=status, left_at=left_at)
            return
        _ = await query.update(using="sync", status=status)

    @classmethod
    async def list_unordered_for_call(cls, call_id: str) -> list[Self]:
        """Участники звонка. Порядка, limit и фильтра компании нет."""
        return await cls.objects.filter(call_id=call_id).all()

    @classmethod
    async def count_joined(cls, call_id: str) -> int:
        return await cls.objects.filter(call_id=call_id, status="joined").count()
