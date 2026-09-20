"""Репозиторий durable-лога PlatformEvent."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from apps.realtime.db.base import RealtimeDatabase
from apps.realtime.db.models import PlatformEventLogRow
from core.db.utils import get_rowcount
from core.events.contract import EventDelivery, PlatformEvent, PlatformEventMeta
from core.realtime.models import BusProcessingState
from core.types import JsonObject, require_json_object


class PlatformEventLogRepository:
    def __init__(self, db: RealtimeDatabase) -> None:
        self._db: RealtimeDatabase = db

    async def insert_if_absent(
        self,
        event: PlatformEvent,
        *,
        processing_state: BusProcessingState,
        owner_service: str | None,
        deadline_at: datetime | None,
    ) -> bool:
        """True — вставлена новая строка. False — event_id уже был."""
        delivery_payload: JsonObject | None = None
        if event.delivery is not None:
            delivery_payload = require_json_object(
                event.delivery.model_dump(mode="json"),
                "PlatformEvent.delivery",
            )
        stmt = (
            insert(PlatformEventLogRow)
            .values(
                event_id=event.event_id,
                type=event.type,
                company_id=event.company_id,
                payload=event.payload,
                meta=require_json_object(event.meta.model_dump(mode="json"), "PlatformEvent.meta"),
                delivery=delivery_payload,
                processing_state=processing_state.value,
                owner_service=owner_service,
                causation_id=event.meta.causation_id,
                deadline_at=deadline_at,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
        async with self._db.session() as session:
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result) == 1

    async def get(self, event_id: str) -> PlatformEvent | None:
        async with self._db.session() as session:
            row = await session.get(PlatformEventLogRow, event_id)
        if row is None:
            return None
        return _row_to_event(row)

    async def set_processing_state(
        self,
        event_id: str,
        processing_state: BusProcessingState,
    ) -> None:
        async with self._db.session() as session:
            row = await session.get(PlatformEventLogRow, event_id)
            if row is None:
                raise ValueError(f"platform_event_log row {event_id!r} not found")
            row.processing_state = processing_state.value
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def list_expired_commands(self, *, now: datetime, limit: int) -> list[PlatformEvent]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        stmt = (
            select(PlatformEventLogRow)
            .where(PlatformEventLogRow.deadline_at.is_not(None))
            .where(PlatformEventLogRow.deadline_at < now)
            .where(
                PlatformEventLogRow.processing_state.in_(
                    [
                        BusProcessingState.RECEIVED.value,
                        BusProcessingState.DISPATCHED.value,
                    ]
                )
            )
            .order_by(PlatformEventLogRow.deadline_at.asc())
            .limit(limit)
        )
        async with self._db.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_event(row) for row in rows]

    async def has_terminal_for_causation(self, causation_id: str) -> bool:
        stmt = (
            select(PlatformEventLogRow.event_id)
            .where(PlatformEventLogRow.causation_id == causation_id)
            .where(
                or_(
                    PlatformEventLogRow.type.like("%_succeeded"),
                    PlatformEventLogRow.type.like("%_failed"),
                )
            )
            .limit(1)
        )
        async with self._db.session() as session:
            found = (await session.execute(stmt)).scalar_one_or_none()
        return found is not None

    async def get_terminal_for_causation(self, causation_id: str) -> PlatformEvent | None:
        stmt = (
            select(PlatformEventLogRow)
            .where(PlatformEventLogRow.causation_id == causation_id)
            .where(
                or_(
                    PlatformEventLogRow.type.like("%_succeeded"),
                    PlatformEventLogRow.type.like("%_failed"),
                )
            )
            .order_by(PlatformEventLogRow.created_at.desc())
            .limit(1)
        )
        async with self._db.session() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _row_to_event(row)


def _row_to_event(row: PlatformEventLogRow) -> PlatformEvent:
    delivery: EventDelivery | None = None
    if row.delivery is not None:
        delivery = EventDelivery.model_validate(row.delivery)
    return PlatformEvent(
        event_id=row.event_id,
        type=row.type,
        company_id=row.company_id,
        payload=row.payload,
        meta=PlatformEventMeta.model_validate(row.meta),
        delivery=delivery,
    )
