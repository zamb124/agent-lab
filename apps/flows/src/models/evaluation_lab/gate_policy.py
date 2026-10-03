"""Таблица evaluation lab: gate_policy.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import CompanyScopedModel


class EvaluationGatePolicy(CompanyScopedModel):
    """Порог качества ветки набора. Таблица ``evaluation_gate_policies``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_gate_policies"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "suite_id", "branch_id", "name"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
        ]

    gate_policy_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    name: str = DbField()
    min_pass_rate: float = DbField(ge=0.0, le=1.0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    min_average_score: float | None = DbField(default=None, ge=0.0, le=10.0)
    max_failed_case_runs: int = DbField(default=0, ge=0)
    max_error_case_runs: int = DbField(default=0, ge=0)
    max_average_duration_ms: int | None = DbField(default=None, ge=0)
    require_baseline: bool = DbField(default=False)
    min_baseline_score_delta: float | None = DbField(default=None)
    max_baseline_duration_delta_ms: int | None = DbField(default=None, ge=0)
    archived_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_for_suite(cls, suite_id: str) -> list[Self]:
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await cls.objects.filter(suite_id=suite_id).order_by("branch_id", "name").all()
