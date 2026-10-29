"""Таблица durable execution."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.durable_execution.models.contracts import (
    ActivityStatus,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class ActivityAttempt(PlatformModel):
    """Попытка команды. Таблица ``activity_attempts``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "activity_attempts"
        unique_together: list[tuple[str, str]] = [("activity_id", "attempt")]
        indexes: list[Index] = [
            Index(["activity_id"]),
            Index(["execution_branch_id", "status"]),
            Index(["company_id", "session_id"]),
        ]

    activity_attempt_id: str = DbField(db_pk=True, db_type="TEXT")
    activity_id: str = DbField(db_type="TEXT")
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    attempt: int = DbField(ge=1)
    status: ActivityStatus = DbField()
    scheduled_at: datetime = DbField()
    result_json: JsonObject | None = DbField(default=None, db_type="JSONB")
    error: str | None = DbField(default=None, db_type="TEXT")
    lease_until: datetime | None = DbField(default=None)
    started_at: datetime | None = DbField(default=None)
    completed_at: datetime | None = DbField(default=None)

    @classmethod
    async def latest_by_attempt_desc(cls, activity_id: str, *, for_update: bool) -> Self | None:
        """Последняя попытка activity, ORDER BY attempt DESC. Несколько с одним attempt — какая именно, не задано. Нет строки — None."""
        query = cls.objects.filter(activity_id=activity_id).order_by("-attempt")
        if for_update:
            query = query.for_update()
        return await query.first()
