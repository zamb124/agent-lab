"""
Репозиторий единого журнала задач CRM (crm_tasks).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast as type_cast
from typing import override

from sqlalchemy import func, select, update
from sqlalchemy.sql import ColumnElement

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import CRMTask
from core.context import get_context
from core.types import JsonObject, SqlParameterValue

CRM_TASK_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "rolled_back"})


class TaskRepository(BaseCRMRepository[CRMTask]):
    @property
    @override
    def model_class(self) -> type[CRMTask]:
        return CRMTask

    @property
    @override
    def id_field(self) -> str:
        return "task_id"

    @override
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    @staticmethod
    def _data_text_path_expression(key: str) -> ColumnElement[str]:
        return type_cast(ColumnElement[str], func.jsonb_extract_path_text(CRMTask.data, key))

    @override
    async def create(self, entity: CRMTask) -> CRMTask:
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
        return entity

    @override
    async def get(self, task_id: str, /, *, company_id: str | None = None) -> CRMTask | None:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.task_id == task_id,
                CRMTask.company_id == cid,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_for_worker(self, task_id: str, company_id: str) -> CRMTask | None:
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
        status: str | None = None,
        stage: str | None = None,
        progress_pct: int | None = None,
        error_message: str | None = None,
        data_patch: JsonObject | None = None,
        cancel_requested: bool | None = None,
        taskiq_task_id: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        values: dict[str, SqlParameterValue] = {"updated_at": datetime.now(UTC)}
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
            if status == "running":
                base_where.append(
                    CRMTask.status.not_in(("completed", "failed", "cancelled", "rolled_back"))
                )
            # Завершение из воркера не перетирает уже финализированную запись
            # (пользователь успел отменить через API, пока воркер дописывал результат)
            _worker_terminal = ("completed", "failed", "cancelled")
            if status in _worker_terminal:
                base_where.append(CRMTask.status.in_(("pending", "running")))
            if data_patch:
                _ = await session.execute(
                    update(CRMTask)
                    .where(*base_where)
                    .values(data=CRMTask.data.op("||")(data_patch), **values)
                )
            else:
                _ = await session.execute(update(CRMTask).where(*base_where).values(**values))
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
            now = datetime.now(UTC)
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
            now = datetime.now(UTC)
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
        namespace: str | None,
        *,
        task_type: str | None = None,
        note_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        company_id: str | None = None,
    ) -> list[CRMTask]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMTask).where(CRMTask.company_id == cid)
            if namespace is not None:
                stmt = stmt.where(CRMTask.namespace == namespace)
            if task_type is not None:
                stmt = stmt.where(CRMTask.task_type == task_type)
            if note_id is not None:
                stmt = stmt.where(self._data_text_path_expression("note_id") == note_id)
            stmt = stmt.order_by(CRMTask.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_for_namespace(
        self,
        namespace: str | None,
        *,
        task_type: str | None = None,
        note_id: str | None = None,
        company_id: str | None = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(CRMTask).where(CRMTask.company_id == cid)
            if namespace is not None:
                stmt = stmt.where(CRMTask.namespace == namespace)
            if task_type is not None:
                stmt = stmt.where(CRMTask.task_type == task_type)
            if note_id is not None:
                stmt = stmt.where(self._data_text_path_expression("note_id") == note_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def find_active_by_data_keys(
        self,
        task_type: str,
        data_key_values: dict[str, str],
        namespace: str,
        company_id: str,
    ) -> CRMTask | None:
        """Найти активную (pending/running) задачу по типу и значениям JSONB-полей data."""
        async with self._db.session() as session:
            stmt = select(CRMTask).where(
                CRMTask.company_id == company_id,
                CRMTask.namespace == namespace,
                CRMTask.task_type == task_type,
                CRMTask.status.in_(("pending", "running")),
            )
            for key, value in data_key_values.items():
                stmt = stmt.where(self._data_text_path_expression(key) == value)
            stmt = stmt.order_by(CRMTask.created_at.desc()).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def count_in_progress_for_namespace(
        self,
        namespace: str,
        *,
        task_type: str | None = None,
        company_id: str | None = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(CRMTask)
                .where(
                    CRMTask.company_id == cid,
                    CRMTask.namespace == namespace,
                    CRMTask.status.in_(("pending", "running")),
                )
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
        company_id: str | None = None,
    ) -> int:
        """Только knowledge_import задачи ожидающие ревью.

        review_completed_at хранится в JSONB data. JSON null даёт SQL NULL
        при использовании ->>; проверяем именно IS NULL.
        """
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(CRMTask)
                .where(
                    CRMTask.company_id == cid,
                    CRMTask.namespace == namespace,
                    CRMTask.task_type == "knowledge_import",
                    CRMTask.status.in_(("completed", "failed", "cancelled")),
                    self._data_text_path_expression("review_completed_at").is_(None),
                )
            )
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Task awaiting_review count returned empty")
            return int(value)
