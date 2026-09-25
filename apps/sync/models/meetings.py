"""Запись звонка Sync: таблица и ответ API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel

from core.models.platform_model import PlatformModel

RecordingStatus = Literal["requested", "recording", "uploaded", "failed"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SyncCallRecording(PlatformModel):
    """Строка ``sync_call_recordings``, алиас ``sync``, ``__global_model__``.

    ``call_id`` и ``channel_id`` ссылаются на звонок и канал (ещё SQLAlchemy).
    ``raw_file_id`` ссылается на ``sync_files.file_id`` ON DELETE SET NULL.
    В ``0001`` эти внешние ключи остаются. Ответ API — ``CallRecordingRead``:
    там закрытый статус и ссылки на файл, которых нет в колонках.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_call_recordings"
        indexes: list[Index] = [
            Index(["company_id"]),
            Index(["call_id"]),
            Index(["channel_id"]),
            Index(["status"]),
            Index(["company_id", "namespace"]),
        ]

    recording_id: str = DbField(db_pk=True, max_length=64)
    call_id: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100)
    channel_id: str = DbField(max_length=64)
    namespace: str = DbField(max_length=100)
    status: str = DbField(default="requested", max_length=24)
    created_at: datetime = DbField(default_factory=_utcnow)
    started_by_user_id: str | None = DbField(default=None, max_length=64)
    provider_job_id: str | None = DbField(default=None, max_length=128)
    storage_id: str = DbField(default="platform", max_length=64)
    raw_file_id: str | None = DbField(default=None, max_length=64)
    started_at: datetime | None = DbField(default=None)
    ended_at: datetime | None = DbField(default=None)
    error: str | None = DbField(default=None, db_type="TEXT")

    @classmethod
    async def mark_call_recording_status(
        cls,
        recording_id: str,
        *,
        status: str,
        provider_job_id: str | None = None,
        raw_file_id: str | None = None,
        error: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        query = cls.objects.filter(recording_id=recording_id)
        if provider_job_id is not None or raw_file_id is not None:
            if provider_job_id is None or raw_file_id is None or error is not None or ended_at is not None:
                raise ValueError("recording status patch fields do not match a known update")
            _ = await query.update(
                using="sync",
                status=status,
                provider_job_id=provider_job_id,
                raw_file_id=raw_file_id,
            )
            return
        if error is not None:
            if ended_at is not None:
                raise ValueError("recording status patch fields do not match a known update")
            _ = await query.update(using="sync", status=status, error=error)
            return
        if ended_at is not None:
            _ = await query.update(using="sync", status=status, ended_at=ended_at)
            return
        _ = await query.update(using="sync", status=status)

    @classmethod
    async def list_for_call(cls, call_id: str, company_id: str) -> list[Self]:
        return await cls.objects.filter(
            call_id=call_id,
            company_id=company_id,
        ).order_by("-created_at").all()

    @classmethod
    async def active_for_call(cls, call_id: str, company_id: str) -> Self | None:
        return await cls.objects.filter(
            call_id=call_id,
            company_id=company_id,
            status__in=["requested", "recording"],
        ).get_or_none()


class CallRecordingRead(BaseModel):
    recording_id: str
    call_id: str
    channel_id: str
    namespace: str
    started_by_user_id: str | None = None
    status: RecordingStatus
    provider_job_id: str | None = None
    raw_file_id: str | None = None
    raw_file_storage_url: str | None = None
    raw_file_download_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    error: str | None = None
