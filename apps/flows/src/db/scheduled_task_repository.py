"""
Репозиторий для работы с scheduled tasks.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from apps.flows.src.db.models import ScheduledTasks
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.scheduler.models import (
    ContentType,
    ScheduledTaskInfo,
    ScheduledTaskStatus,
    ScheduleType,
)

logger = get_logger(__name__)


class ScheduledTaskRepository:
    """Репозиторий для работы с scheduled tasks в PostgreSQL."""

    def __init__(self, storage):
        self._storage = storage

    async def save(self, task: ScheduledTaskInfo) -> str:
        """
        Сохраняет scheduled task.

        Returns:
            ID задачи
        """
        async with self._storage.get_session() as session:
            stmt = (
                insert(ScheduledTasks)
                .values(
                    id=task.id,
                    schedule_id=task.schedule_id,
                    flow_id=task.flow_id,
                    session_id=task.session_id,
                    user_id=task.user_id,
                    schedule_type=task.schedule_type.value
                    if hasattr(task.schedule_type, "value")
                    else task.schedule_type,
                    content_type=task.content_type.value
                    if hasattr(task.content_type, "value")
                    else task.content_type,
                    cron=task.cron,
                    interval_minutes=task.interval_minutes,
                    run_at=task.run_at,
                    content=task.content,
                    tool_args=task.tool_args,
                    description=task.description,
                    status=task.status.value if hasattr(task.status, "value") else task.status,
                    created_at=task.created_at,
                    executed_at=task.executed_at,
                    next_run=task.next_run,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "schedule_id": task.schedule_id,
                        "status": task.status.value
                        if hasattr(task.status, "value")
                        else task.status,
                        "executed_at": task.executed_at,
                        "next_run": task.next_run,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()
            return task.id

    async def get_by_id(self, task_id: str) -> ScheduledTaskInfo | None:
        """Получает задачу по ID."""
        async with self._storage.get_session() as session:
            stmt = select(ScheduledTasks).where(ScheduledTasks.id == task_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if not row:
                return None

            return self._row_to_task_info(row)

    async def get_by_session(
        self, session_id: str, status: ScheduledTaskStatus | None = None
    ) -> list[ScheduledTaskInfo]:
        """Получает задачи по session_id."""
        async with self._storage.get_session() as session:
            stmt = select(ScheduledTasks).where(ScheduledTasks.session_id == session_id)

            if status:
                stmt = stmt.where(ScheduledTasks.status == status.value)

            stmt = stmt.order_by(ScheduledTasks.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [self._row_to_task_info(row) for row in rows]

    async def get_by_flow(
        self, flow_id: str, status: ScheduledTaskStatus | None = None
    ) -> list[ScheduledTaskInfo]:
        """Получает задачи по flow_id."""
        async with self._storage.get_session() as session:
            stmt = select(ScheduledTasks).where(ScheduledTasks.flow_id == flow_id)

            if status:
                stmt = stmt.where(ScheduledTasks.status == status.value)

            stmt = stmt.order_by(ScheduledTasks.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [self._row_to_task_info(row) for row in rows]

    async def update_status(
        self,
        task_id: str,
        status: ScheduledTaskStatus,
        executed_at: datetime | None = None,
        next_run: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Обновляет статус задачи."""
        async with self._storage.get_session() as session:
            values: dict[str, Any] = {"status": status.value}

            if executed_at:
                values["executed_at"] = executed_at
            if next_run is not None:
                values["next_run"] = next_run
            if error_message:
                values["error_message"] = error_message

            stmt = update(ScheduledTasks).where(ScheduledTasks.id == task_id).values(**values)

            result = await session.execute(stmt)
            await session.commit()

            return get_rowcount(result) > 0

    async def delete(self, task_id: str) -> bool:
        """Удаляет задачу."""
        async with self._storage.get_session() as session:
            stmt = delete(ScheduledTasks).where(ScheduledTasks.id == task_id)
            result = await session.execute(stmt)
            await session.commit()

            return get_rowcount(result) > 0

    def _row_to_task_info(self, row: ScheduledTasks) -> ScheduledTaskInfo:
        """Конвертирует строку БД в ScheduledTaskInfo."""
        return ScheduledTaskInfo(
            id=row.id,
            schedule_id=row.schedule_id,
            flow_id=row.flow_id,
            session_id=row.session_id,
            user_id=row.user_id,
            schedule_type=ScheduleType(row.schedule_type),
            content_type=ContentType(row.content_type),
            cron=row.cron,
            interval_minutes=row.interval_minutes,
            run_at=row.run_at,
            content=row.content,
            tool_args=row.tool_args,
            description=row.description,
            status=ScheduledTaskStatus(row.status),
            created_at=row.created_at,
            executed_at=row.executed_at,
            next_run=row.next_run,
            error_message=row.error_message,
        )
