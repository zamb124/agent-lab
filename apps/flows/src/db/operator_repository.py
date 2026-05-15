"""
Репозиторий очередей и задач оператора (PostgreSQL, сервис flows).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy import delete, func, select, update

from apps.flows.src.db.models import OperatorQueueMembers, OperatorQueues, OperatorTasks


class OperatorRepository:
    """CRUD для operator_queues, operator_queue_members, operator_tasks."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    async def create_queue(
        self,
        *,
        company_id: str,
        name: str,
        slug: str,
        description: Optional[str] = None,
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
        async with self._storage._get_session() as session:
            session.add(row)
            await session.commit()
        return qid

    async def get_queue_by_id(self, company_id: str, queue_id: str) -> Optional[OperatorQueues]:
        async with self._storage._get_session() as session:
            return await session.scalar(
                select(OperatorQueues).where(
                    OperatorQueues.id == queue_id,
                    OperatorQueues.company_id == company_id,
                )
            )

    async def get_queue_by_slug(self, company_id: str, slug: str) -> Optional[OperatorQueues]:
        async with self._storage._get_session() as session:
            return await session.scalar(
                select(OperatorQueues).where(
                    OperatorQueues.company_id == company_id,
                    OperatorQueues.slug == slug,
                )
            )

    async def list_queues(self, company_id: str) -> Sequence[OperatorQueues]:
        async with self._storage._get_session() as session:
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
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if not values:
            return
        async with self._storage._get_session() as session:
            await session.execute(
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
        async with self._storage._get_session() as session:
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
        async with self._storage._get_session() as session:
            await session.execute(
                delete(OperatorQueueMembers).where(
                    OperatorQueueMembers.queue_id == queue_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            await session.commit()

    async def count_members(self, queue_id: str) -> int:
        async with self._storage._get_session() as session:
            n = await session.scalar(
                select(func.count())
                .select_from(OperatorQueueMembers)
                .where(OperatorQueueMembers.queue_id == queue_id)
            )
            return int(n or 0)

    async def is_user_member_of_queue(self, queue_id: str, user_id: str) -> bool:
        async with self._storage._get_session() as session:
            row = await session.scalar(
                select(OperatorQueueMembers.id).where(
                    OperatorQueueMembers.queue_id == queue_id,
                    OperatorQueueMembers.user_id == user_id,
                )
            )
            return row is not None

    async def list_user_ids_for_queue(self, queue_id: str) -> List[str]:
        async with self._storage._get_session() as session:
            result = await session.execute(
                select(OperatorQueueMembers.user_id).where(
                    OperatorQueueMembers.queue_id == queue_id,
                )
            )
            return list(result.scalars().all())

    async def list_queue_ids_for_user(self, company_id: str, user_id: str) -> List[str]:
        async with self._storage._get_session() as session:
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
    ) -> Optional[OperatorTasks]:
        async with self._storage._get_session() as session:
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
    ) -> Optional[OperatorTasks]:
        async with self._storage._get_session() as session:
            return await session.scalar(
                select(OperatorTasks).where(
                    OperatorTasks.company_id == company_id,
                    OperatorTasks.correlation_id == correlation_id,
                )
            )

    async def insert_task(self, row: OperatorTasks) -> None:
        async with self._storage._get_session() as session:
            session.add(row)
            await session.commit()

    async def list_tasks(
        self,
        company_id: str,
        *,
        queue_id: Optional[str] = None,
        queue_ids: Optional[Sequence[str]] = None,
        status: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Tuple[List[OperatorTasks], int]:
        async with self._storage._get_session() as session:
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
        status: Optional[str] = None,
        claimed_by_user_id: Any = ...,
        resolution_payload: Optional[dict[str, Any]] = None,
    ) -> None:
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
        if claimed_by_user_id is not ...:
            values["claimed_by_user_id"] = claimed_by_user_id
        if resolution_payload is not None:
            values["resolution_payload"] = resolution_payload
        if not values:
            return
        values["updated_at"] = datetime.now(timezone.utc)
        async with self._storage._get_session() as session:
            await session.execute(
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
        entry: dict[str, Any],
    ) -> None:
        """Атомарно добавляет реплику в dialog_log (JSONB append)."""
        async with self._storage._get_session() as session:
            task = await session.scalar(
                select(OperatorTasks).where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
            )
            if task is None:
                raise ValueError(f"Задача {task_id!r} не найдена")
            log: list[dict[str, Any]] = list(task.dialog_log) if task.dialog_log else []
            log.append(entry)
            await session.execute(
                update(OperatorTasks)
                .where(
                    OperatorTasks.id == task_id,
                    OperatorTasks.company_id == company_id,
                )
                .values(dialog_log=log, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def get_dialog_log(
        self,
        company_id: str,
        task_id: str,
    ) -> list[dict[str, Any]]:
        """Возвращает dialog_log задачи."""
        task = await self.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача {task_id!r} не найдена")
        return list(task.dialog_log) if task.dialog_log else []
