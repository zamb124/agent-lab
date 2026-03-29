"""Репозиторий записей звонков и встреч."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncCallMeeting, SyncCallRecording, SyncCallSpeakerSegment


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


class CallMeetingRepository(BaseSyncRepository[SyncCallMeeting]):
    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    def model_class(self) -> type[SyncCallMeeting]:
        return SyncCallMeeting

    @property
    def id_field(self) -> str:
        return "meeting_id"

    async def list_meetings(
        self,
        *,
        company_id: str,
        channel_id: str | None,
        space_id: str | None,
        limit: int,
    ) -> list[SyncCallMeeting]:
        async with self._db.session() as session:
            stmt = select(SyncCallMeeting).where(SyncCallMeeting.company_id == company_id)
            if channel_id is not None:
                stmt = stmt.where(SyncCallMeeting.channel_id == channel_id)
            if space_id is not None:
                stmt = stmt.where(SyncCallMeeting.space_id == space_id)
            result = await session.execute(stmt.order_by(SyncCallMeeting.created_at.desc()).limit(limit))
            return list(result.scalars().all())

    async def get_by_recording(self, recording_id: str, company_id: str) -> SyncCallMeeting | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(SyncCallMeeting).where(
                    SyncCallMeeting.recording_id == recording_id,
                    SyncCallMeeting.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()

    async def update_summary(self, meeting_id: str, summary_json: dict[str, object]) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(SyncCallMeeting)
                .where(SyncCallMeeting.meeting_id == meeting_id)
                .values(summary_json=summary_json, updated_at=datetime.now(UTC))
            )
            await session.commit()

    async def set_export_status(
        self,
        meeting_id: str,
        *,
        status: str,
        target_namespace: str | None,
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(SyncCallMeeting)
                .where(SyncCallMeeting.meeting_id == meeting_id)
                .values(
                    export_status=status,
                    export_target_namespace=target_namespace,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()


class CallSpeakerSegmentRepository(BaseSyncRepository[SyncCallSpeakerSegment]):
    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    def model_class(self) -> type[SyncCallSpeakerSegment]:
        return SyncCallSpeakerSegment

    @property
    def id_field(self) -> str:
        return "segment_id"

    async def list_for_meeting(self, meeting_id: str, company_id: str) -> list[SyncCallSpeakerSegment]:
        async with self._db.session() as session:
            result = await session.execute(
                select(SyncCallSpeakerSegment)
                .where(
                    SyncCallSpeakerSegment.meeting_id == meeting_id,
                    SyncCallSpeakerSegment.company_id == company_id,
                )
                .order_by(SyncCallSpeakerSegment.started_ms.asc())
            )
            return list(result.scalars().all())

    async def replace_for_meeting(
        self,
        *,
        meeting_id: str,
        company_id: str,
        segments: list[SyncCallSpeakerSegment],
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(SyncCallSpeakerSegment)
                .where(
                    SyncCallSpeakerSegment.meeting_id == meeting_id,
                    SyncCallSpeakerSegment.company_id == company_id,
                )
            )
            for segment in segments:
                session.add(segment)
            await session.commit()
