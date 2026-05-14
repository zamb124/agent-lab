"""
Репозиторий единого журнала задач CRM (crm_tasks).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select, update

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import CRMTask
from core.context import get_context

CRM_TASK_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "rolled_back"})


class TaskRepository(BaseCRMRepository[CRMTask]):
    @property
    def model_class(self) -> type[CRMTask]:
        return CRMTask

    @property
    def id_field(self) -> str:
        return "task_id"

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    async def create(self, row: CRMTask) -> CRMTask:
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def get(self, task_id: str, *, company_id: Optional[str] = None) -> Optional[CRMTask]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.task_id == task_id,
                CRMTask.company_id == cid,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_for_worker(self, task_id: str, company_id: str) -> Optional[CRMTask]:
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.task_id == task_id,
                CRMTask.company_id == company_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def patch_progress(
        self,
        task_id: str,
        company_id: str,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress_pct: Optional[int] = None,
        error_message: Optional[str] = None,
        data_patch: Optional[dict[str, Any]] = None,
        cancel_requested: Optional[bool] = None,
        taskiq_task_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if status is not None:
            values["status"] = status
        if stage is not None:
            values["stage"] = stage
        if progress_pct is not None:
            values["progress_pct"] = progress_pct
        if error_message is not None:
            values["error_message"] = error_message
        if cancel_requested is not None:
            values["cancel_requested"] = cancel_requested
        if taskiq_task_id is not None:
            values["taskiq_task_id"] = taskiq_task_id
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at

        async with self._db.session() as session:
            base_where = [CRMTask.task_id == task_id, CRMTask.company_id == company_id]
            # Переход в "running" не должен перезаписывать уже терминальные статусы
            # (race condition: kiq() с sync_tools выполняется in-process до возврата)
            if values.get("status") == "running":
                base_where.append(
                    CRMTask.status.not_in(("completed", "failed", "cancelled", "rolled_back"))
                )
            # Завершение из воркера не перетирает уже финализированную запись
            # (пользователь успел отменить через API, пока воркер дописывал результат)
            _worker_terminal = ("completed", "failed", "cancelled")
            if values.get("status") in _worker_terminal:
                base_where.append(CRMTask.status.in_(("pending", "running")))
            if data_patch:
                await session.execute(
                    update(CRMTask)
                    .where(*base_where)
                    .values(data=CRMTask.data.op("||")(data_patch), **values)
                )
            else:
                await session.execute(
                    update(CRMTask)
                    .where(*base_where)
                    .values(**values)
                )
            await session.commit()

    async def reconcile_cancel_requested_active_tasks(self) -> list[CRMTask]:
        """``pending``/``running`` с ``cancel_requested`` → ``cancelled`` (воркер не подхватил отмену).

        Без порога по ``updated_at``: после рестарта не ждём ``STALE_CRM_TASK_INACTIVITY``.
        """
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.status.in_(("pending", "running")),
                CRMTask.cancel_requested.is_(True),
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            now = datetime.now(timezone.utc)
            for row in rows:
                row.status = "cancelled"
                row.stage = "cancelled"
                row.completed_at = now
                row.cancel_requested = False
                row.error_message = None
                row.updated_at = now
            await session.commit()
            for row in rows:
                await session.refresh(row)
        return rows

    async def reconcile_stale_active_tasks_older_than(self, *, cutoff: datetime) -> list[CRMTask]:
        """Активные задачи без обновления status/progress дольше cutoff → failed.

        Запись с ``cancel_requested`` при старте воркера обрабатывается отдельно в
        ``reconcile_cancel_requested_active_tasks`` (без порога по времени).

        cancel_requested в этом методе — запасной путь для строк, попавших под cutoff.
        """
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.status.in_(("pending", "running")),
                CRMTask.updated_at < cutoff,
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            now = datetime.now(timezone.utc)
            msg_failed = (
                "Задача прервана: нет активности воркера (перезапуск сервиса или сбой процесса)."
            )
            for row in rows:
                if row.cancel_requested:
                    row.status = "cancelled"
                    row.stage = "cancelled"
                    row.completed_at = now
                    row.cancel_requested = False
                    row.error_message = None
                else:
                    row.status = "failed"
                    row.stage = "failed"
                    row.progress_pct = 100
                    row.completed_at = now
                    row.error_message = msg_failed
                row.updated_at = now
            await session.commit()
            for row in rows:
                await session.refresh(row)
        return rows

    async def list_for_namespace(
        self,
        namespace: Optional[str],
        *,
        task_type: Optional[str] = None,
        note_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[CRMTask]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMTask).where(CRMTask.company_id == cid)
            if namespace is not None:
                stmt = stmt.where(CRMTask.namespace == namespace)
            if task_type is not None:
                stmt = stmt.where(CRMTask.task_type == task_type)
            if note_id is not None:
                stmt = stmt.where(CRMTask.data["note_id"].as_string() == note_id)
            stmt = stmt.order_by(CRMTask.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_for_namespace(
        self,
        namespace: Optional[str],
        *,
        task_type: Optional[str] = None,
        note_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMTask).where(CRMTask.company_id == cid)
            if namespace is not None:
                stmt = stmt.where(CRMTask.namespace == namespace)
            if task_type is not None:
                stmt = stmt.where(CRMTask.task_type == task_type)
            if note_id is not None:
                stmt = stmt.where(CRMTask.data["note_id"].as_string() == note_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def find_active_by_data_keys(
        self,
        task_type: str,
        data_key_values: dict[str, str],
        namespace: str,
        company_id: str,
    ) -> Optional[CRMTask]:
        """Найти активную (pending/running) задачу по типу и значениям JSONB-полей data."""
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.company_id == company_id,
                CRMTask.namespace == namespace,
                CRMTask.task_type == task_type,
                CRMTask.status.in_(("pending", "running")),
            )
            for key, value in data_key_values.items():
                stmt = stmt.where(CRMTask.data[key].as_string() == value)
            stmt = stmt.order_by(CRMTask.created_at.desc()).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def count_in_progress_for_namespace(
        self,
        namespace: str,
        *,
        task_type: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMTask).where(
                CRMTask.company_id == cid,
                CRMTask.namespace == namespace,
                CRMTask.status.in_(("pending", "running")),
            )
            if task_type is not None:
                stmt = stmt.where(CRMTask.task_type == task_type)
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Task in_progress count returned empty")
            return int(value)

    async def count_awaiting_review_for_namespace(
        self,
        namespace: str,
        *,
        company_id: Optional[str] = None,
    ) -> int:
        """Только knowledge_import задачи ожидающие ревью.

        review_completed_at хранится в JSONB data. JSON null даёт SQL NULL
        при использовании ->>; проверяем именно IS NULL.
        """
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMTask).where(
                CRMTask.company_id == cid,
                CRMTask.namespace == namespace,
                CRMTask.task_type == "knowledge_import",
                CRMTask.status.in_(("completed", "failed", "cancelled")),
                CRMTask.data["review_completed_at"].as_string().is_(None),
            )
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Task awaiting_review count returned empty")
            return int(value)
