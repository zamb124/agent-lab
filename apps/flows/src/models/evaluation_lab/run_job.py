"""Таблица evaluation lab: run_job.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import IntegrityError

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationRunJobState,
)
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationRunJob(CompanyScopedModel):
    """Очередь запуска прогона. Таблица ``evaluation_run_jobs``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_run_jobs"
        unique_together: list[tuple[str, str]] = [
            ("company_id", "run_id"),
            ("company_id", "taskiq_task_id"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "state", "created_at"]),
        ]

    run_job_id: str = DbField(db_pk=True)
    run_id: str = DbField()
    taskiq_task_id: str = DbField()
    state: EvaluationRunJobState = DbField()
    context_data: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    trace_context: JsonObject | None = DbField(default=None, db_type="JSONB")
    error: str | None = DbField(default=None, db_type="TEXT")
    enqueued_at: datetime | None = DbField(default=None)

    @classmethod
    async def for_run(cls, run_id: str) -> Self | None:
        if run_id == "":
            raise ValueError("run_id is required")
        return await cls.objects.filter(run_id=run_id).first()

    @classmethod
    async def list_pending(cls, limit: int) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be positive")
        return await (
            cls.objects.filter(state=EvaluationRunJobState.PENDING)
            .order_by("created_at", "run_job_id")
            .limit(limit)
            .all()
        )

    @classmethod
    async def insert_for_run(cls, job: Self) -> Self:
        if job.run_id == "":
            raise ValueError("run_id is required")
        existing = await cls.for_run(job.run_id)
        if existing is not None:
            return existing
        try:
            _ = await cls.set(job)
        except IntegrityError:
            stored = await cls.for_run(job.run_id)
            if stored is None:
                raise
            return stored
        return job
