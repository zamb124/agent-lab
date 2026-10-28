"""Трек LiveKit egress «речь в ленту»."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncCallSpeechEgressTrack(PlatformModel):
    """Строка ``sync_call_speech_egress_tracks``, алиас ``sync``, ``__global_model__``.

    ``call_id`` и ``channel_id`` ссылаются на звонок и канал. Внешние ключи в модели
    не объявлены. В ``0001`` они остаются ON DELETE CASCADE. Уникальность
    ``egress_id`` и пары ``(call_id, track_sid)``.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_call_speech_egress_tracks"
        indexes: list[Index] = [
            Index(["call_id"]),
            Index(["company_id"]),
        ]
        unique_together: list[tuple[str, str]] = [("call_id", "track_sid")]

    row_id: str = DbField(db_pk=True, max_length=64)
    call_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    channel_id: str = DbField(max_length=64)
    participant_identity: str = DbField(max_length=200)
    track_sid: str = DbField(max_length=128)
    egress_id: str = DbField(max_length=128, db_unique=True)
    storage_id: str = DbField(default="platform", max_length=64)
    segments_posted: int = DbField(default=0)
    created_at: datetime = DbField(default_factory=_utcnow)
    last_segment_s3_key: str | None = DbField(default=None, max_length=1024)

    @classmethod
    async def mark_speech_egress_segments(
        cls,
        row_id: str,
        segments_posted: int,
        last_segment_s3_key: str | None,
    ) -> None:
        rows = await cls.objects.filter(row_id=row_id).update(
            returning=True,
            using="sync",
            segments_posted=segments_posted,
            last_segment_s3_key=last_segment_s3_key,
        )
        if len(rows) != 1:
            raise ValueError(f"Speech egress row {row_id} not found.")

    @classmethod
    async def by_call_and_track(cls, call_id: str, track_sid: str) -> Self | None:
        return await cls.objects.filter(
            call_id=call_id,
            track_sid=track_sid,
        ).get_or_none()

    @classmethod
    async def list_by_created_at_asc_for_call(cls, call_id: str, company_id: str) -> list[Self]:
        """Сегменты речи звонка компании, ORDER BY created_at по возрастанию. Предела нет."""
        return await cls.objects.filter(
            call_id=call_id,
            company_id=company_id,
        ).order_by("created_at").all()

    @classmethod
    async def delete_for_call(cls, call_id: str, company_id: str) -> None:
        _ = await cls.objects.filter(
            call_id=call_id,
            company_id=company_id,
        ).delete()
