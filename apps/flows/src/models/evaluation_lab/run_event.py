"""Таблица evaluation lab: run_event.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationEventType,
)
from apps.flows.src.models.evaluation_lab.run import (
    EvaluationRun,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationRunEvent(CompanyScopedModel):
    """Событие прогона. Таблица ``evaluation_run_events``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_run_events"
        unique_together: list[tuple[str, str, str]] = [("company_id", "run_id", "sequence")]
        indexes: list[Index] = [
            Index(["company_id", "run_id"]),
        ]

    event_id: str = DbField(db_pk=True)
    run_id: str = DbField()
    sequence: int = DbField()
    event_type: EvaluationEventType = DbField()
    payload: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    case_run_id: str | None = DbField(default=None)

    @classmethod
    async def list_for_run(cls, run_id: str) -> list[Self]:
        if run_id == "":
            raise ValueError("run_id is required")
        return await cls.objects.filter(run_id=run_id).order_by("sequence").all()

    @classmethod
    async def list_after(
        cls,
        run_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> list[Self]:
        if run_id == "":
            raise ValueError("run_id is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        return await (
            cls.objects.filter(run_id=run_id, sequence__gt=after_sequence)
            .order_by("sequence")
            .limit(limit)
            .all()
        )

    @classmethod
    async def next_sequence(cls, run_id: str) -> int:
        if run_id == "":
            raise ValueError("run_id is required")
        latest = await cls.objects.filter(run_id=run_id).order_by("-sequence").first()
        if latest is None:
            return 1
        return latest.sequence + 1

    @classmethod
    async def append(cls, event: Self) -> Self:
        if event.run_id == "":
            raise ValueError("run_id is required")
        async with atomic(using="flows"):
            locked = await (
                EvaluationRun.objects.filter(run_id=event.run_id).for_update().first()
            )
            if locked is None:
                raise ValueError(f"Evaluation run not found: {event.run_id}")
            stored = event.model_copy(update={"sequence": await cls.next_sequence(event.run_id)})
            _ = await cls.set(stored)
        return stored

class EvaluationRunEventsPage(StrictBaseModel):
    items: list[EvaluationRunEvent]
    next_sequence: int | None = None
    has_more: bool
