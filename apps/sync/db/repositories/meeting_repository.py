"""Репозиторий записей звонков."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncCallRecording


class CallRecordingRepository(BaseSyncRepository[SyncCallRecording]):
    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    def model_class(self) -> type[SyncCallRecording]:
        return SyncCallRecording

    @property
    def id_field(self) -> str:
        return "recording_id"

    async def list_for_call(self, call_id: str, company_id: str) -> list[SyncCallRecording]:
        async with self._db.session() as session:
            result = await session.execute(
                select(SyncCallRecording)
                .where(
                    SyncCallRecording.call_id == call_id,
                    SyncCallRecording.company_id == company_id,
                )
                .order_by(SyncCallRecording.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_active_for_call(self, call_id: str, company_id: str) -> SyncCallRecording | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(SyncCallRecording).where(
                    SyncCallRecording.call_id == call_id,
                    SyncCallRecording.company_id == company_id,
                    SyncCallRecording.status.in_(["requested", "recording"]),
                )
            )
            return result.scalar_one_or_none()

    async def mark_status(
        self,
        recording_id: str,
        *,
        status: str,
        provider_job_id: str | None = None,
        raw_file_id: str | None = None,
        error: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if provider_job_id is not None:
            values["provider_job_id"] = provider_job_id
        if raw_file_id is not None:
            values["raw_file_id"] = raw_file_id
        if error is not None:
            values["error"] = error
        if ended_at is not None:
            values["ended_at"] = ended_at
        async with self._db.session() as session:
            await session.execute(
                update(SyncCallRecording)
                .where(SyncCallRecording.recording_id == recording_id)
                .values(**values)
            )
            await session.commit()
