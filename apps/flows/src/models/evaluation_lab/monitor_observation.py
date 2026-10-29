"""Таблица evaluation lab: monitor_observation.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.case import (
    EvaluationCase,
)
from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationMonitorObservationState,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationMonitorObservation(CompanyScopedModel):
    """Сэмпл трейса монитора. Таблица ``evaluation_monitor_observations``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_monitor_observations"
        unique_together: list[tuple[str, str, str]] = [("company_id", "monitor_id", "trace_id")]
        indexes: list[Index] = [
            Index(["company_id", "monitor_id", "sampled_at"]),
            Index(["company_id", "trace_id"]),
        ]

    observation_id: str = DbField(db_pk=True)
    monitor_id: str = DbField()
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    trace_id: str = DbField()
    state: EvaluationMonitorObservationState = DbField()
    span_count: int = DbField(ge=0)
    payload: JsonObject = DbField(db_type="JSONB")
    sampled_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    task_id: str | None = DbField(default=None)
    session_id: str | None = DbField(default=None)
    curated_case_id: str | None = DbField(default=None)

    @classmethod
    async def for_trace(
        cls,
        monitor_id: str,
        trace_id: str,
    ) -> Self | None:
        if monitor_id == "" or trace_id == "":
            raise ValueError("monitor_id and trace_id are required")
        return await cls.objects.filter(
            monitor_id=monitor_id,
            trace_id=trace_id,
        ).get_or_none()

    @classmethod
    async def list_for_monitor_by_sampled_at_desc(cls, monitor_id: str, limit: int) -> list[Self]:
        """Наблюдения монитора, ORDER BY sampled_at DESC, observation_id DESC, не больше limit. Пустой monitor_id — ValueError monitor_id is required. limit < 1 — ValueError limit must be >= 1."""
        if monitor_id == "":
            raise ValueError("monitor_id is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return await (
            cls.objects.filter(monitor_id=monitor_id)
            .order_by("-sampled_at", "-observation_id")
            .limit(limit)
            .all()
        )

    @classmethod
    async def upsert_by_monitor_and_trace(cls, observation: Self) -> Self:
        existing = await cls.for_trace(observation.monitor_id, observation.trace_id)
        if existing is None:
            _ = await cls.set(observation)
            stored = await cls.for_trace(observation.monitor_id, observation.trace_id)
            if stored is None:
                raise RuntimeError("evaluation monitor observation upsert did not persist")
            return stored
        existing.task_id = observation.task_id
        existing.session_id = observation.session_id
        if existing.curated_case_id is None:
            existing.state = observation.state
        existing.span_count = observation.span_count
        existing.payload = observation.payload
        existing.sampled_at = observation.sampled_at
        _ = await existing.save()
        return existing

class EvaluationMonitorObservationCurationResult(StrictBaseModel):
    case: EvaluationCase
    observation: EvaluationMonitorObservation
