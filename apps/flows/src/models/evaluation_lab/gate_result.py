"""Таблица evaluation lab: gate_result.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationGateState,
)
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationGateResult(CompanyScopedModel):
    """Итог применения политики к прогону. Таблица ``evaluation_gate_results``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_gate_results"
        unique_together: list[tuple[str, str]] = [("company_id", "run_id")]
        indexes: list[Index] = [
            Index(["company_id", "gate_policy_id"]),
        ]

    gate_result_id: str = DbField(db_pk=True)
    run_id: str = DbField()
    gate_policy_id: str = DbField()
    state: EvaluationGateState = DbField()
    metrics: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    violations: list[str] = DbField(default_factory=list, db_type="JSONB")

    @classmethod
    async def for_run(cls, run_id: str) -> Self | None:
        if run_id == "":
            raise ValueError("run_id is required")
        return await cls.objects.filter(run_id=run_id).get_or_none()
