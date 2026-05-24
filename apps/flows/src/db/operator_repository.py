"""
Репозиторий очередей и задач оператора (PostgreSQL, сервис flows).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from apps.flows.src.db.models import OperatorQueueMembers, OperatorQueues, OperatorTasks
from apps.flows.src.models.operator_schemas import (
    OperatorDialogLogEntry,
    OperatorResolutionPayload,
)
from core.db.storage import Storage
from core.types import JsonArray, JsonObject, parse_json_object


class OperatorRepository:
    """CRUD для operator_queues, operator_queue_members, operator_tasks."""

    def __init__(self, storage: Storage) -> None:
        self._storage: Storage = storage

    async def create_queue(
        self,
        *,
        company_id: str,
        name: str,
        slug: str,
        description: str | None = None,
    ) -> str:
        if await self.get_queue_by_slug(company_id, slug) is not None:
            raise ValueError(f"Очередь со slug {slug!r} уже существует для компании")
        qid = str(uuid.uuid4())
        row = OperatorQueues(
            id=qid,
            company_id=company_id,
            name=name,
            slug=slug,
            description=description,
        )
        async with self._storage.get_session() as session:
            session.add(row)
            await session.commit()
        return qid

    async def get_queue_by_id(self, company_id: str, queue_id: str) -> OperatorQueues | None:
        async with self._storage.get_session() as session:
            return await session.scalar(
                select(OperatorQueues).where(
                    OperatorQueues.id == queue_id,
                    OperatorQueues.company_id == company_id,
                )
            )

    async def get_queue_by_slug(self, company_id: str, slug: str) -> OperatorQueues | None:
        async with self._storage.get_session() as session:
            return await session.scalar(
                select(OperatorQueues).where(
                    OperatorQueues.company_id == company_id,
                    OperatorQueues.slug == slug,
                )
            )

    async def list_queues(self, company_id: str) -> Sequence[OperatorQueues]:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(OperatorQueues)
                .where(OperatorQueues.company_id == company_id)
                .order_by(OperatorQueues.name)
            )
            return result.scalars().all()

    async def update_queue(
        self,
        company_id: str,
        queue_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        values: dict[str, str] = {}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if not values:
            return
        async with self._storage.get_session() as session:
            _ = await session.execute(
                update(OperatorQueues)
                .where(
                    OperatorQueues.id == queue_id,
                    OperatorQueues.company_id == company_id,
                )
                .values(**values)
            )
            await session.commit()

    async def add_member(
        self,
        queue_id: str,
        user_id: str,
        role: str = "agent",
    ) -> str:
        async with self._storage.get_session() as session:
            existing = await session.scalar(
                select(OperatorQueueMembers).where(
                    OperatorQueueMembers.queue_id == queue_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            if existing is not None:
                return existing.id
            mid = str(uuid.uuid4())
            row = OperatorQueueMembers(
                id=mid, queue_id=queue_id, user_id=user_id, role=role
            )
            session.add(row)
            await session.commit()
            return mid

    async def remove_member(self, queue_id: str, user_id: str) -> None:
        async with self._storage.get_session() as session:
            _ = await session.execute(
                delete(OperatorQueueMembers).where(
                    OperatorQueueMembers.queue_id == queue_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            await session.commit()

    async def count_members(self, queue_id: str) -> int:
        async with self._storage.get_session() as session:
            n = await session.scalar(
                select(func.count())
                .select_from(OperatorQueueMembers)
                .where(OperatorQueueMembers.queue_id == queue_id)
            )
            return int(n or 0)

    async def is_user_member_of_queue(self, queue_id: str, user_id: str) -> bool:
        async with self._storage.get_session() as session:
            row = await session.scalar(
                select(OperatorQueueMembers.id).where(
                    OperatorQueueMembers.queue_id == queue_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            return row is not None

    async def list_user_ids_for_queue(self, queue_id: str) -> list[str]:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(OperatorQueueMembers.user_id).where(
                    OperatorQueueMembers.queue_id == queue_id,
                )
            )
            return list(result.scalars().all())

    async def list_queue_ids_for_user(self, company_id: str, user_id: str) -> list[str]:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(OperatorQueueMembers.queue_id)
                .join(OperatorQueues, OperatorQueues.id == OperatorQueueMembers.queue_id)
                .where(
                    OperatorQueues.company_id == company_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            return list(result.scalars().all())

    async def get_task(
        self,
        company_id: str,
        task_id: str,
    ) -> OperatorTasks | None:
        async with self._storage.get_session() as session:
            return await session.scalar(
                select(OperatorTasks).where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
            )

    async def get_task_by_correlation(
        self,
        company_id: str,
        correlation_id: str,
    ) -> OperatorTasks | None:
        async with self._storage.get_session() as session:
            return await session.scalar(
                select(OperatorTasks).where(
                    OperatorTasks.company_id == company_id,
                    OperatorTasks.correlation_id == correlation_id,
                )
            )

    async def insert_task(self, row: OperatorTasks) -> None:
        async with self._storage.get_session() as session:
            session.add(row)
            await session.commit()

    async def list_tasks(
        self,
        company_id: str,
        *,
        queue_id: str | None = None,
        queue_ids: Sequence[str] | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[OperatorTasks], int]:
        async with self._storage.get_session() as session:
            q = select(OperatorTasks).where(OperatorTasks.company_id == company_id)
            if queue_id is not None:
                q = q.where(OperatorTasks.queue_id == queue_id)
            if queue_ids is not None:
                q = q.where(OperatorTasks.queue_id.in_(list(queue_ids)))
            if status is not None:
                q = q.where(OperatorTasks.status == status)
            count_q = select(func.count()).select_from(OperatorTasks).where(
                OperatorTasks.company_id == company_id
            )
            if queue_id is not None:
                count_q = count_q.where(OperatorTasks.queue_id == queue_id)
            if queue_ids is not None:
                count_q = count_q.where(OperatorTasks.queue_id.in_(list(queue_ids)))
            if status is not None:
                count_q = count_q.where(OperatorTasks.status == status)
            total = int((await session.execute(count_q)).scalar_one())
            q = (
                q.order_by(OperatorTasks.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(q)).scalars().all()
            return list(rows), total

    async def update_task_fields(
        self,
        company_id: str,
        task_id: str,
        *,
        status: str | None = None,
        claimed_by_user_id: str | None = None,
        resolution_payload: OperatorResolutionPayload | None = None,
    ) -> None:
        values: dict[str, str | JsonObject | datetime] = {}
        if status is not None:
            values["status"] = status
        if claimed_by_user_id is not None:
            values["claimed_by_user_id"] = claimed_by_user_id
        if resolution_payload is not None:
            values["resolution_payload"] = parse_json_object(
                resolution_payload.model_dump_json(),
                "OperatorResolutionPayload",
            )
        if not values:
            return
        values["updated_at"] = datetime.now(timezone.utc)
        async with self._storage.get_session() as session:
            _ = await session.execute(
                update(OperatorTasks)
                .where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
                .values(**values)
            )
            await session.commit()

    async def append_dialog_log(
        self,
        company_id: str,
        task_id: str,
        entry: OperatorDialogLogEntry,
    ) -> None:
        """Атомарно добавляет реплику в dialog_log (JSONB append)."""
        async with self._storage.get_session() as session:
            task = await session.scalar(
                select(OperatorTasks).where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
            )
            if task is None:
                raise ValueError(f"Задача {task_id!r} не найдена")
            log = (
                [OperatorDialogLogEntry.model_validate(item) for item in task.dialog_log]
                if task.dialog_log
                else []
            )
            log.append(entry)
            log_payload: JsonArray = [
                parse_json_object(item.model_dump_json(), "OperatorDialogLogEntry")
                for item in log
            ]
            _ = await session.execute(
                update(OperatorTasks)
                .where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
                .values(dialog_log=log_payload, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def get_dialog_log(
        self,
        company_id: str,
        task_id: str,
    ) -> list[OperatorDialogLogEntry]:
        """Возвращает dialog_log задачи."""
        task = await self.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача {task_id!r} не найдена")
        if not task.dialog_log:
            return []
        return [OperatorDialogLogEntry.model_validate(item) for item in task.dialog_log]
