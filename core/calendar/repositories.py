"""
SQL-репозитории календаря (shared БД).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models import CalendarEventRecord, CalendarIntegrationRecord
from core.models import (
    CalendarAttendee,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarExternalRef,
    CalendarIntegration,
    CalendarIntegrationCredentials,
    CalendarIntegrationSettings,
    CalendarProvider,
)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _event_from_record(record: CalendarEventRecord) -> CalendarEvent:
    return CalendarEvent(
        event_id=record.event_id,
        source=CalendarEventSource(record.source),
        source_id=record.source_id,
        company_id=record.company_id,
        namespace=record.namespace,
        kind=record.kind,
        title=record.title,
        description=record.description,
        location=record.location,
        status=CalendarEventStatus(record.status),
        timezone=record.timezone,
        all_day=record.all_day,
        start_at=record.start_at,
        end_at=record.end_at,
        attendees=[CalendarAttendee.model_validate(item) for item in record.attendees],
        recurrence_rule=record.recurrence_rule,
        recurrence_id=record.recurrence_id,
        series_id=record.series_id,
        deep_link=record.deep_link,
        external_refs=[CalendarExternalRef.model_validate(item) for item in record.external_refs],
        metadata={str(key): str(value) for key, value in record.metadata_json.items()},
        created_by_user_id=record.created_by_user_id,
        updated_by_user_id=record.updated_by_user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _integration_from_record(record: CalendarIntegrationRecord) -> CalendarIntegration:
    return CalendarIntegration(
        integration_id=record.integration_id,
        company_id=record.company_id,
        user_id=record.user_id,
        provider=CalendarProvider(record.provider),
        credentials=CalendarIntegrationCredentials.model_validate(record.credentials),
        settings=CalendarIntegrationSettings.model_validate(record.settings),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class CalendarEventSqlRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    async def get(self, event_id: str, company_id: str) -> CalendarEvent | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CalendarEventRecord).where(
                    CalendarEventRecord.event_id == event_id,
                    CalendarEventRecord.company_id == company_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _event_from_record(row)

    async def upsert(self, event: CalendarEvent) -> None:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "event_id": event.event_id,
            "company_id": event.company_id,
            "source": _enum_value(event.source),
            "source_id": event.source_id,
            "namespace": event.namespace,
            "kind": event.kind,
            "title": event.title,
            "description": event.description,
            "location": event.location,
            "status": _enum_value(event.status),
            "timezone": event.timezone,
            "all_day": event.all_day,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "attendees": [item.model_dump(mode="json") for item in event.attendees],
            "recurrence_rule": event.recurrence_rule,
            "recurrence_id": event.recurrence_id,
            "series_id": event.series_id,
            "deep_link": event.deep_link,
            "external_refs": [item.model_dump(mode="json") for item in event.external_refs],
            "metadata_json": event.metadata,
            "created_by_user_id": event.created_by_user_id,
            "updated_by_user_id": event.updated_by_user_id,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
        }
        stmt = insert(CalendarEventRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id"],
            set_={
                "company_id": stmt.excluded.company_id,
                "source": stmt.excluded.source,
                "source_id": stmt.excluded.source_id,
                "namespace": stmt.excluded.namespace,
                "kind": stmt.excluded.kind,
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "location": stmt.excluded.location,
                "status": stmt.excluded.status,
                "timezone": stmt.excluded.timezone,
                "all_day": stmt.excluded.all_day,
                "start_at": stmt.excluded.start_at,
                "end_at": stmt.excluded.end_at,
                "attendees": stmt.excluded.attendees,
                "recurrence_rule": stmt.excluded.recurrence_rule,
                "recurrence_id": stmt.excluded.recurrence_id,
                "series_id": stmt.excluded.series_id,
                "deep_link": stmt.excluded.deep_link,
                "external_refs": stmt.excluded.external_refs,
                "metadata": stmt.excluded["metadata"],
                "created_by_user_id": stmt.excluded.created_by_user_id,
                "updated_by_user_id": stmt.excluded.updated_by_user_id,
                "created_at": stmt.excluded.created_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete(self, event_id: str, company_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(CalendarEventRecord).where(
                    CalendarEventRecord.event_id == event_id,
                    CalendarEventRecord.company_id == company_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def list_in_range(self, company_id: str, start_at: datetime, end_at: datetime, limit: int) -> list[CalendarEvent]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CalendarEventRecord)
                .where(
                    CalendarEventRecord.company_id == company_id,
                    and_(CalendarEventRecord.start_at < end_at, CalendarEventRecord.end_at > start_at),
                )
                .order_by(CalendarEventRecord.start_at.asc())
                .limit(limit)
            )
            rows = list(result.scalars().all())
            return [_event_from_record(item) for item in rows]


class CalendarIntegrationSqlRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    async def list_by_user(self, company_id: str, user_id: str) -> list[CalendarIntegration]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CalendarIntegrationRecord)
                .where(
                    CalendarIntegrationRecord.company_id == company_id,
                    CalendarIntegrationRecord.user_id == user_id,
                )
                .order_by(CalendarIntegrationRecord.created_at.asc())
            )
            rows = list(result.scalars().all())
            return [_integration_from_record(item) for item in rows]

    async def list_sync_enabled(
        self,
        *,
        limit: int,
    ) -> list[CalendarIntegration]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            sync_enabled_expr = CalendarIntegrationRecord.settings["sync_enabled"].astext
            result = await session.execute(
                select(CalendarIntegrationRecord)
                .where(
                    CalendarIntegrationRecord.provider.in_(
                        [
                            CalendarProvider.GOOGLE.value,
                            CalendarProvider.YANDEX.value,
                        ]
                    ),
                    or_(sync_enabled_expr == "true", sync_enabled_expr.is_(None)),
                )
                .order_by(CalendarIntegrationRecord.updated_at.asc())
                .limit(limit)
            )
            rows = list(result.scalars().all())
            return [_integration_from_record(item) for item in rows]

    async def get_by_user_provider(self, company_id: str, user_id: str, provider: CalendarProvider) -> CalendarIntegration | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CalendarIntegrationRecord).where(
                    CalendarIntegrationRecord.company_id == company_id,
                    CalendarIntegrationRecord.user_id == user_id,
                    CalendarIntegrationRecord.provider == provider.value,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _integration_from_record(row)

    async def upsert(self, integration: CalendarIntegration) -> None:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "integration_id": integration.integration_id,
            "company_id": integration.company_id,
            "user_id": integration.user_id,
            "provider": _enum_value(integration.provider),
            "credentials": integration.credentials.model_dump(mode="json"),
            "settings": integration.settings.model_dump(mode="json"),
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
        }
        stmt = insert(CalendarIntegrationRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["integration_id"],
            set_={
                "company_id": stmt.excluded.company_id,
                "user_id": stmt.excluded.user_id,
                "provider": stmt.excluded.provider,
                "credentials": stmt.excluded.credentials,
                "settings": stmt.excluded.settings,
                "created_at": stmt.excluded.created_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete(self, integration_id: str, company_id: str, user_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(CalendarIntegrationRecord).where(
                    CalendarIntegrationRecord.integration_id == integration_id,
                    CalendarIntegrationRecord.company_id == company_id,
                    CalendarIntegrationRecord.user_id == user_id,
                )
            )
            await session.commit()
            return result.rowcount > 0
