"""Журнал фоновых задач CRM."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Query, execute_raw

from core.models.platform_model import PlatformModel
from core.types import JsonObject, parse_json_object, require_json_object

CRM_TASK_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "rolled_back"})
_RUNNING_GUARD = "status NOT IN ('completed', 'failed', 'cancelled', 'rolled_back')"
_WORKER_TERMINAL_GUARD = "status IN ('pending', 'running')"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CRMTask(PlatformModel):
    """Строка ``crm_tasks``. Ответ API — эта же модель."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crm_tasks"
        indexes: list[Index] = [
            Index(["company_id", "namespace", "status"]),
        ]

    task_id: str = DbField(db_pk=True, max_length=100)
    task_type: str = DbField(max_length=64)
    company_id: str = DbField(max_length=100, db_index=True)
    namespace: str = DbField(max_length=100, db_index=True)
    user_id: str = DbField(max_length=100)
    created_at: datetime = DbField(default_factory=_utcnow)
    updated_at: datetime = DbField(default_factory=_utcnow)
    status: str = DbField(default="pending", max_length=32, db_index=True)
    stage: str = DbField(default="pending", max_length=64)
    progress_pct: int = DbField(default=0)
    error_message: str | None = DbField(default=None, db_type="TEXT")
    data: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    taskiq_task_id: str | None = DbField(default=None, max_length=220)
    cancel_requested: bool = DbField(default=False)
    started_at: datetime | None = DbField(default=None)
    completed_at: datetime | None = DbField(default=None)

    @classmethod
    async def create(cls, task: Self) -> Self:
        return await cls.objects.create(instance=task)

    @classmethod
    def namespace_tasks(
        cls,
        company_id: str,
        namespace: str | None,
        task_type: str | None,
    ) -> Query[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if namespace is not None:
            rows = rows.filter(namespace=namespace)
        if task_type is not None:
            rows = rows.filter(task_type=task_type)
        return rows

    @classmethod
    async def by_company_and_task_id(
        cls,
        company_id: str,
        task_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            task_id=task_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def patch_progress(
        cls,
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
        table = cls.get_table_name()
        now = datetime.now(UTC)
        assignments = ["updated_at = $3"]
        params: list[str | int | datetime | bool | None] = [task_id, company_id, now]

        def bind(column: str, value: str | int | datetime | bool | None) -> None:
            params.append(value)
            assignments.append(f"{column} = ${len(params)}")

        if status is not None:
            bind("status", status)
        if stage is not None:
            bind("stage", stage)
        if progress_pct is not None:
            bind("progress_pct", progress_pct)
        if error_message is not None:
            bind("error_message", error_message)
        if cancel_requested is not None:
            bind("cancel_requested", cancel_requested)
        if taskiq_task_id is not None:
            bind("taskiq_task_id", taskiq_task_id)
        if started_at is not None:
            bind("started_at", started_at)
        if completed_at is not None:
            bind("completed_at", completed_at)
        if data_patch is not None:
            params.append(json.dumps(data_patch))
            assignments.append(f"data = data || ${len(params)}::jsonb")
        where = ["task_id = $1", "company_id = $2"]
        if status == "running":
            where.append(_RUNNING_GUARD)
        if status in ("completed", "failed", "cancelled"):
            where.append(_WORKER_TERMINAL_GUARD)
        _ = await execute_raw(
            "UPDATE "
            + table
            + " SET "
            + ", ".join(assignments)
            + " WHERE "
            + " AND ".join(where),
            params,
            using="crm",
        )

    @classmethod
    async def cancel_if_requested(cls) -> list[CRMTask]:
        table = cls.get_table_name()
        now = datetime.now(UTC)
        rows = await execute_raw(
            "UPDATE "
            + table
            + " SET status = 'cancelled', stage = 'cancelled', "
            + "completed_at = $1, cancel_requested = false, error_message = NULL, updated_at = $1 "
            + "WHERE status IN ('pending', 'running') AND cancel_requested "
            + "RETURNING row_to_json("
            + table
            + ") AS item",
            [now],
            using="crm",
        )
        return [_task_from_row(row) for row in rows]

    @classmethod
    async def close_stale(cls, *, cutoff: datetime) -> list[CRMTask]:
        table = cls.get_table_name()
        now = datetime.now(UTC)
        message = "Задача прервана: нет активности воркера (перезапуск сервиса или сбой процесса)."
        rows = await execute_raw(
            "UPDATE "
            + table
            + " SET "
            + "status = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'failed' END, "
            + "stage = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'failed' END, "
            + "progress_pct = CASE WHEN cancel_requested THEN progress_pct ELSE 100 END, "
            + "completed_at = $1, cancel_requested = false, "
            + "error_message = CASE WHEN cancel_requested THEN NULL ELSE $2 END, "
            + "updated_at = $1 "
            + "WHERE status IN ('pending', 'running') AND updated_at < $3 "
            + "RETURNING row_to_json("
            + table
            + ") AS item",
            [now, message, cutoff],
            using="crm",
        )
        return [_task_from_row(row) for row in rows]

    @classmethod
    async def list_by_note_id(
        cls,
        *,
        company_id: str,
        namespace: str | None,
        task_type: str | None,
        note_id: str,
        limit: int,
        offset: int,
    ) -> list[CRMTask]:
        table = cls.get_table_name()
        where_sql, params = _note_filter(company_id, namespace, task_type, note_id)
        params.append(limit)
        limit_placeholder = f"${len(params)}"
        params.append(offset)
        offset_placeholder = f"${len(params)}"
        rows = await execute_raw(
            "SELECT row_to_json("
            + table
            + ") AS item FROM "
            + table
            + f" WHERE {where_sql} ORDER BY created_at DESC "
            + f"LIMIT {limit_placeholder} OFFSET {offset_placeholder}",
            params,
            using="crm",
        )
        return [_task_from_row(row) for row in rows]

    @classmethod
    async def count_by_note_id(
        cls,
        *,
        company_id: str,
        namespace: str | None,
        task_type: str | None,
        note_id: str,
    ) -> int:
        table = cls.get_table_name()
        where_sql, params = _note_filter(company_id, namespace, task_type, note_id)
        rows = await execute_raw(
            "SELECT count(*)::int AS total FROM " + table + " WHERE " + where_sql,
            params,
            using="crm",
        )
        return _count_cell(rows)

    @classmethod
    async def active_by_data_keys(
        cls,
        task_type: str,
        data_key_values: dict[str, str],
        namespace: str,
        company_id: str,
    ) -> CRMTask | None:
        table = cls.get_table_name()
        clauses = [
            "company_id = $1",
            "namespace = $2",
            "task_type = $3",
            "status IN ('pending', 'running')",
        ]
        params: list[str] = [company_id, namespace, task_type]
        for key, value in data_key_values.items():
            params.append(key)
            key_placeholder = f"${len(params)}"
            params.append(value)
            value_placeholder = f"${len(params)}"
            clauses.append(f"data->>{key_placeholder} = {value_placeholder}")
        rows = await execute_raw(
            "SELECT row_to_json("
            + table
            + ") AS item FROM "
            + table
            + " WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT 1",
            params,
            using="crm",
        )
        if len(rows) == 0:
            return None
        return _task_from_row(rows[0])

    @classmethod
    async def count_knowledge_import_in_progress(
        cls,
        namespace: str,
        *,
        company_id: str,
    ) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            task_type="knowledge_import",
            status__in=["pending", "running"],
        ).count()

    @classmethod
    async def count_knowledge_import_awaiting_review(
        cls,
        namespace: str,
        *,
        company_id: str,
    ) -> int:
        table = cls.get_table_name()
        rows = await execute_raw(
            "SELECT count(*)::int AS total FROM "
            + table
            + " WHERE company_id = $1 AND namespace = $2 AND task_type = 'knowledge_import' "
            + "AND status IN ('completed', 'failed', 'cancelled') "
            + "AND data->>'review_completed_at' IS NULL",
            [company_id, namespace],
            using="crm",
        )
        return _count_cell(rows)


def _note_filter(
    company_id: str,
    namespace: str | None,
    task_type: str | None,
    note_id: str,
) -> tuple[str, list[str | int]]:
    clauses = ["company_id = $1"]
    params: list[str | int] = [company_id]
    if namespace is not None:
        params.append(namespace)
        clauses.append(f"namespace = ${len(params)}")
    if task_type is not None:
        params.append(task_type)
        clauses.append(f"task_type = ${len(params)}")
    params.append(note_id)
    clauses.append(f"data->>'note_id' = ${len(params)}")
    return " AND ".join(clauses), params


def _count_cell(rows: Sequence[object]) -> int:
    if len(rows) != 1:
        raise ValueError("crm task count returned empty value")
    total = require_json_object(rows[0], "crm_task_count")["total"]
    if isinstance(total, bool) or not isinstance(total, int):
        raise TypeError("crm task count must be int")
    return total


def _task_from_row(row: object) -> CRMTask:
    parsed = require_json_object(row, "crm_task")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "crm_task")
    else:
        payload = require_json_object(raw_item, "crm_task")
    raw_data = payload.get("data")
    if isinstance(raw_data, str):
        payload["data"] = parse_json_object(raw_data, "crm_task.data")
    return CRMTask.model_validate(payload)
