"""SQL репозиторий scheduler задач в shared БД."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models.platform import SchedulerTaskRecord
from core.db.utils import get_rowcount
from core.scheduler.models import (
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)


def _to_model(record: SchedulerTaskRecord) -> PlatformScheduledTask:
    return PlatformScheduledTask(
        schedule_task_id=record.schedule_task_id,
        company_id=record.company_id,
        schedule_id=record.schedule_id,
        target_service=record.target_service,
        task_name=record.task_name,
        queue_name=record.queue_name,
        schedule_type=PlatformScheduleType(record.schedule_type),
        cron=record.cron,
        interval_seconds=record.interval_seconds,
        run_at=record.run_at,
        timezone=record.timezone,
        payload=record.payload,
        status=ScheduledTaskStatus(record.status),
        created_by_user_id=record.created_by_user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_run_at=record.last_run_at,
        next_run_at=record.next_run_at,
        error_message=record.error_message,
    )


class SchedulerTaskRepository:
    """Репозиторий scheduler task metadata."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    async def save(self, task: PlatformScheduledTask) -> PlatformScheduledTask:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "schedule_task_id": task.schedule_task_id,
            "company_id": task.company_id,
            "schedule_id": task.schedule_id,
            "target_service": task.target_service,
            "task_name": task.task_name,
            "queue_name": task.queue_name,
            "schedule_type": task.schedule_type.value
            if hasattr(task.schedule_type, "value")
            else str(task.schedule_type),
            "cron": task.cron,
            "interval_seconds": task.interval_seconds,
            "run_at": task.run_at,
            "timezone": task.timezone,
            "payload": task.payload,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "created_by_user_id": task.created_by_user_id,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "last_run_at": task.last_run_at,
            "next_run_at": task.next_run_at,
            "error_message": task.error_message,
        }
        stmt = insert(SchedulerTaskRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SchedulerTaskRecord.schedule_task_id],
            set_={
                "schedule_id": stmt.excluded.schedule_id,
                "target_service": stmt.excluded.target_service,
                "task_name": stmt.excluded.task_name,
                "queue_name": stmt.excluded.queue_name,
                "schedule_type": stmt.excluded.schedule_type,
                "cron": stmt.excluded.cron,
                "interval_seconds": stmt.excluded.interval_seconds,
                "run_at": stmt.excluded.run_at,
                "timezone": stmt.excluded.timezone,
                "payload": stmt.excluded.payload,
                "status": stmt.excluded.status,
                "updated_at": stmt.excluded.updated_at,
                "last_run_at": stmt.excluded.last_run_at,
                "next_run_at": stmt.excluded.next_run_at,
                "error_message": stmt.excluded.error_message,
            },
        )
        async with session_factory() as session:
            await session.execute(stmt)
            await session.commit()
        return task

    async def get(self, company_id: str, schedule_task_id: str) -> Optional[PlatformScheduledTask]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(SchedulerTaskRecord).where(
                    SchedulerTaskRecord.company_id == company_id,
                    SchedulerTaskRecord.schedule_task_id == schedule_task_id,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                return None
            return _to_model(record)

    async def list(
        self, company_id: str, filters: PlatformScheduleFilter
    ) -> list[PlatformScheduledTask]:
        session_factory = await get_session_factory(self._db_url)
        stmt = select(SchedulerTaskRecord).where(SchedulerTaskRecord.company_id == company_id)
        if filters.status is not None:
            status_value = (
                filters.status.value if hasattr(filters.status, "value") else str(filters.status)
            )
            stmt = stmt.where(SchedulerTaskRecord.status == status_value)
        if filters.target_service:
            stmt = stmt.where(SchedulerTaskRecord.target_service == filters.target_service)
        if filters.task_name:
            stmt = stmt.where(SchedulerTaskRecord.task_name == filters.task_name)
        stmt = (
            stmt.order_by(SchedulerTaskRecord.created_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )

        async with session_factory() as session:
            result = await session.execute(stmt)
            records = list(result.scalars().all())
            return [_to_model(item) for item in records]

    async def count(self, company_id: str, filters: PlatformScheduleFilter) -> int:
        session_factory = await get_session_factory(self._db_url)
        stmt = (
            select(func.count())
            .select_from(SchedulerTaskRecord)
            .where(SchedulerTaskRecord.company_id == company_id)
        )
        if filters.status is not None:
            status_value = (
                filters.status.value if hasattr(filters.status, "value") else str(filters.status)
            )
            stmt = stmt.where(SchedulerTaskRecord.status == status_value)
        if filters.target_service:
            stmt = stmt.where(SchedulerTaskRecord.target_service == filters.target_service)
        if filters.task_name:
            stmt = stmt.where(SchedulerTaskRecord.task_name == filters.task_name)
        async with session_factory() as session:
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def update_status(
        self,
        company_id: str,
        schedule_task_id: str,
        status: ScheduledTaskStatus | str,
        *,
        schedule_id: Optional[str] = None,
        last_run_at: Optional[datetime] = None,
        next_run_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        status_value = status.value if isinstance(status, ScheduledTaskStatus) else str(status)
        values: dict[str, object] = {
            "status": status_value,
            "updated_at": datetime.now(timezone.utc),
        }
        if schedule_id is not None:
            values["schedule_id"] = schedule_id
        if last_run_at is not None:
            values["last_run_at"] = last_run_at
        if next_run_at is not None:
            values["next_run_at"] = next_run_at
        if error_message is not None:
            values["error_message"] = error_message

        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                update(SchedulerTaskRecord)
                .where(
                    SchedulerTaskRecord.company_id == company_id,
                    SchedulerTaskRecord.schedule_task_id == schedule_task_id,
                )
                .values(**values)
            )
            await session.commit()
            return get_rowcount(result) > 0
