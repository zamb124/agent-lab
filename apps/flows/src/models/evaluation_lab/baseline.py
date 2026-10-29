"""Таблица evaluation lab: baseline.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.run import (
    EvaluationRunComparison,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel


class EvaluationBaseline(CompanyScopedModel):
    """Закреплённый прогон ветки. Таблица ``evaluation_baselines``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_baselines"
        unique_together: list[tuple[str, str, str]] = [("company_id", "suite_id", "branch_id")]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
        ]

    baseline_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    run_id: str = DbField()
    created_by: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)

    @classmethod
    async def for_branch(cls, suite_id: str, branch_id: str) -> Self | None:
        if suite_id == "" or branch_id == "":
            raise ValueError("suite_id and branch_id are required")
        return await cls.objects.filter(suite_id=suite_id, branch_id=branch_id).get_or_none()

    @classmethod
    async def list_by_branch_id_asc(cls, suite_id: str) -> list[Self]:
        """Базовые линии набора, ORDER BY branch_id ASC. Предела нет. Пустой suite_id — ValueError."""
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await cls.objects.filter(suite_id=suite_id).order_by("branch_id").all()

    @classmethod
    async def upsert_by_suite_and_branch(cls, baseline: Self) -> Self:
        existing = await cls.for_branch(baseline.suite_id, baseline.branch_id)
        if existing is None:
            baseline_id = baseline.baseline_id
            if baseline_id == "":
                raise ValueError("EvaluationBaseline baseline_id is required")
            stored_row = await cls.objects.filter(baseline_id=baseline_id).get_or_none()
            if stored_row is None:
                _ = await cls.objects.create(instance=baseline)
            else:
                _ = await baseline.save()
            stored = await cls.for_branch(baseline.suite_id, baseline.branch_id)
            if stored is None:
                raise RuntimeError("evaluation baseline upsert did not persist")
            return stored
        existing.run_id = baseline.run_id
        existing.flow_id = baseline.flow_id
        existing.created_by = baseline.created_by
        existing.updated_at = baseline.updated_at
        _ = await existing.save()
        return existing

class EvaluationBaselineComparison(StrictBaseModel):
    baseline: EvaluationBaseline
    comparison: EvaluationRunComparison
