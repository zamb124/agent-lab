"""Таблица evaluation lab: case_run.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationCaseRunState,
    EvaluationDialogMessage,
    EvaluationScores,
    EvaluationTraceNodeStep,
    EvaluationTraceSpan,
    EvaluationTraceStateDiff,
    EvaluationTraceToolCall,
    EvaluationTraceWorkflowEvent,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel


class EvaluationCaseRun(CompanyScopedModel):
    """Результат одного кейса в прогоне. Таблица ``evaluation_case_runs``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_case_runs"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "run_id", "case_id", "trial_index"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "run_id"]),
            Index(["company_id", "case_id"]),
        ]

    case_run_id: str = DbField(db_pk=True)
    run_id: str = DbField()
    case_id: str = DbField()
    trial_index: int = DbField(ge=1)
    suite_id: str = DbField()
    flow_id: str = DbField()
    branch_id: str = DbField()
    state: EvaluationCaseRunState = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    task_id: str | None = DbField(default=None)
    context_id: str | None = DbField(default=None)
    session_id: str | None = DbField(default=None)
    trace_id: str | None = DbField(default=None)
    duration_ms: int | None = DbField(default=None, ge=0)
    input_tokens: int = DbField(default=0, ge=0)
    output_tokens: int = DbField(default=0, ge=0)
    total_tokens: int = DbField(default=0, ge=0)
    billing_quantity: int = DbField(default=0, ge=0)
    turns_count: int = DbField(default=0, ge=0)
    scores: EvaluationScores | None = DbField(default=None, db_type="JSONB")
    total_score: float | None = DbField(default=None)
    judge_feedback: str | None = DbField(default=None, db_type="TEXT")
    dialog: list[EvaluationDialogMessage] = DbField(default_factory=list, db_type="JSONB")
    error: str | None = DbField(default=None, db_type="TEXT")
    started_at: datetime | None = DbField(default=None)
    finished_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_for_run(cls, run_id: str) -> list[Self]:
        if run_id == "":
            raise ValueError("run_id is required")
        return await (
            cls.objects.filter(run_id=run_id)
            .order_by("case_id", "trial_index", "created_at")
            .all()
        )

class EvaluationCaseRunTrace(StrictBaseModel):
    case_run: EvaluationCaseRun
    spans: list[EvaluationTraceSpan]
    workflow_events: list[EvaluationTraceWorkflowEvent]
    node_steps: list[EvaluationTraceNodeStep]
    tool_calls: list[EvaluationTraceToolCall]
    state_diffs: list[EvaluationTraceStateDiff]

class EvaluationCompareCaseDelta(StrictBaseModel):
    case_id: str
    trial_index: int
    left: EvaluationCaseRun | None
    right: EvaluationCaseRun | None
    score_delta: float | None
    duration_delta_ms: int | None
