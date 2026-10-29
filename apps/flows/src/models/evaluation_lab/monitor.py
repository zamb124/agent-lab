"""Таблица evaluation lab: monitor.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationMonitorFilter,
    EvaluationMonitorState,
)
from apps.flows.src.models.evaluation_lab.monitor_observation import (
    EvaluationMonitorObservation,
)
from apps.flows.src.models.evaluation_lab.run import (
    EvaluationRun,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel


class EvaluationMonitor(CompanyScopedModel):
    """Сэмплер прод-трейсов. Таблица ``evaluation_monitors``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_monitors"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "suite_id", "branch_id", "name"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
            Index(["company_id", "flow_id", "branch_id"]),
        ]

    monitor_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    name: str = DbField()
    state: EvaluationMonitorState = DbField()
    sampling_rate: float = DbField(ge=0.0, le=1.0)
    max_traces_per_sample: int = DbField(ge=1, le=500)
    created_by: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    filter: EvaluationMonitorFilter = DbField(
        default_factory=EvaluationMonitorFilter,
        db_type="JSONB",
    )
    gate_policy_id: str | None = DbField(default=None)

    @classmethod
    async def list_by_updated_at_desc_and_monitor_id_asc(cls, suite_id: str) -> list[Self]:
        """Мониторы набора, ORDER BY updated_at DESC, monitor_id ASC. Предела нет. Пустой suite_id — ValueError."""
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await (
            cls.objects.filter(suite_id=suite_id).order_by("-updated_at", "monitor_id").all()
        )

    @classmethod
    async def list_active_by_updated_at_and_monitor_id_asc(cls, limit: int) -> list[Self]:
        """Активные мониторы, ORDER BY updated_at, monitor_id ASC, не больше limit. limit < 1 — ValueError limit must be >= 1."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return await (
            cls.objects.filter(state=EvaluationMonitorState.ACTIVE)
            .order_by("updated_at", "monitor_id")
            .limit(limit)
            .all()
        )

class EvaluationMonitorSampleResult(StrictBaseModel):
    monitor: EvaluationMonitor
    observations: list[EvaluationMonitorObservation]

class EvaluationMonitorCycleResult(StrictBaseModel):
    monitor: EvaluationMonitor
    observations: list[EvaluationMonitorObservation]
    run: EvaluationRun | None = None

class EvaluationActiveMonitorCyclesResult(StrictBaseModel):
    cycles: list[EvaluationMonitorCycleResult]
