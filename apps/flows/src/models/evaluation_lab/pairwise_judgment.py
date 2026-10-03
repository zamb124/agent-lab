"""Таблица evaluation lab: pairwise_judgment.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Q

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationPairwiseJudgeMode,
    EvaluationPairwisePreference,
    EvaluationScores,
)
from core.models.platform_model import CompanyScopedModel


class EvaluationPairwiseJudgment(CompanyScopedModel):
    """Сравнение двух прогонов кейса. Таблица ``evaluation_pairwise_judgments``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_pairwise_judgments"
        indexes: list[Index] = [
            Index(["company_id", "suite_id", "created_at"]),
            Index(["company_id", "left_case_run_id"]),
            Index(["company_id", "right_case_run_id"]),
        ]

    pairwise_judgment_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    left_run_id: str = DbField()
    right_run_id: str = DbField()
    left_case_run_id: str = DbField()
    right_case_run_id: str = DbField()
    mode: EvaluationPairwiseJudgeMode = DbField()
    preferred: EvaluationPairwisePreference = DbField()
    created_by: str = DbField()
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    rubric_version_id: str | None = DbField(default=None)
    scores: EvaluationScores = DbField(default_factory=dict, db_type="JSONB")
    feedback: str = DbField(default="")

    @classmethod
    async def list_for_case_run(cls, case_run_id: str) -> list[Self]:
        if case_run_id == "":
            raise ValueError("case_run_id is required")
        return await (
            cls.objects.filter(Q(left_case_run_id=case_run_id) | Q(right_case_run_id=case_run_id))
            .order_by("-created_at", "-pairwise_judgment_id")
            .all()
        )
