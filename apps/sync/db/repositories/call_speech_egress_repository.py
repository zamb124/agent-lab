"""Репозиторий строк egress «речь в ленту» по трекам LiveKit."""

from __future__ import annotations

from sqlalchemy import delete, select

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncCallSpeechEgressTrack


class _SegmentsS3CursorUnset:
    pass


_SEGMENTS_S3_CURSOR_UNSET = _SegmentsS3CursorUnset()


class CallSpeechEgressTrackRepository(BaseSyncRepository[SyncCallSpeechEgressTrack]):
    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db)

    @property
    def model_class(self) -> type[SyncCallSpeechEgressTrack]:
        return SyncCallSpeechEgressTrack

    @property
    def id_field(self) -> str:
        return "row_id"

    async def create(self, entity: SyncCallSpeechEgressTrack) -> SyncCallSpeechEgressTrack:
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity

    async def get_by_call_and_track(self, call_id: str, track_sid: str) -> SyncCallSpeechEgressTrack | None:
        async with self._db.session() as session:
            stmt = select(SyncCallSpeechEgressTrack).where(
                SyncCallSpeechEgressTrack.call_id == call_id,
                SyncCallSpeechEgressTrack.track_sid == track_sid,
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def get_by_egress_id(self, egress_id: str) -> SyncCallSpeechEgressTrack | None:
        async with self._db.session() as session:
            stmt = select(SyncCallSpeechEgressTrack).where(
                SyncCallSpeechEgressTrack.egress_id == egress_id,
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def list_for_call(self, call_id: str, company_id: str) -> list[SyncCallSpeechEgressTrack]:
        async with self._db.session() as session:
            stmt = (
                select(SyncCallSpeechEgressTrack)
                .where(
                    SyncCallSpeechEgressTrack.call_id == call_id,
                    SyncCallSpeechEgressTrack.company_id == company_id,
                )
                .order_by(SyncCallSpeechEgressTrack.created_at.asc())
            )
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def set_segments_posted(
        self,
        row_id: str,
        value: int,
        *,
        last_segment_s3_key: str | None | _SegmentsS3CursorUnset = _SEGMENTS_S3_CURSOR_UNSET,
    ) -> None:
        async with self._db.session() as session:
            ent = await session.get(SyncCallSpeechEgressTrack, row_id)
            if ent is None:
                raise ValueError(f"Строка speech egress {row_id} не найдена.")
            ent.segments_posted = value
            if not isinstance(last_segment_s3_key, _SegmentsS3CursorUnset):
                ent.last_segment_s3_key = last_segment_s3_key
            await session.commit()

    async def delete_for_call(self, call_id: str, company_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(SyncCallSpeechEgressTrack).where(
                    SyncCallSpeechEgressTrack.call_id == call_id,
                    SyncCallSpeechEgressTrack.company_id == company_id,
                )
            )
            await session.commit()
