"""Таблица evaluation lab: run.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.case_run import (
    EvaluationCaseRun,
    EvaluationCompareCaseDelta,
)
from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationGateState,
    EvaluationRunCasesScope,
    EvaluationRunState,
    EvaluationRunSuiteScope,
    EvaluationRunTrigger,
)
from apps.flows.src.models.evaluation_lab.gate_result import (
    EvaluationGateResult,
)
from core.context import require_active_company
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel


class EvaluationRun(CompanyScopedModel):
    """Прогон набора. Таблица ``evaluation_runs``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_runs"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "suite_id", "branch_id", "idempotency_key"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
            Index(["company_id", "flow_id", "branch_id"]),
        ]

    run_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    suite_version_id: str = DbField()
    flow_id: str = DbField()
    flow_config_version: str = DbField()
    branch_id: str = DbField()
    trigger: EvaluationRunTrigger = DbField()
    scope: EvaluationRunSuiteScope | EvaluationRunCasesScope = DbField(
        db_type="JSONB",
        discriminator="type",
    )
    state: EvaluationRunState = DbField()
    total_cases: int = DbField()
    total_case_runs: int = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    idempotency_key: str | None = DbField(default=None)
    taskiq_task_id: str | None = DbField(default=None)
    gate_policy_id: str | None = DbField(default=None)
    gate_state: EvaluationGateState | None = DbField(default=None)
    trials: int = DbField(default=1, ge=1)
    max_concurrency: int = DbField(default=1, ge=1)
    passed_case_runs: int = DbField(default=0)
    failed_case_runs: int = DbField(default=0)
    error_case_runs: int = DbField(default=0)
    canceled_case_runs: int = DbField(default=0)
    average_score: float | None = DbField(default=None)
    average_duration_ms: float | None = DbField(default=None)
    input_tokens: int = DbField(default=0, ge=0)
    output_tokens: int = DbField(default=0, ge=0)
    total_tokens: int = DbField(default=0, ge=0)
    billing_quantity: int = DbField(default=0, ge=0)
    started_at: datetime | None = DbField(default=None)
    finished_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_by_created_at_and_run_id_desc(cls, suite_id: str, limit: int) -> list[Self]:
        """Запуски набора, ORDER BY created_at DESC, run_id DESC, не больше limit. Пустой suite_id и limit < 1 — ValueError."""
        if suite_id == "":
            raise ValueError("suite_id is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        return await (
            cls.objects.filter(suite_id=suite_id)
            .order_by("-created_at", "-run_id")
            .limit(limit)
            .all()
        )

    @classmethod
    async def any_for_idempotency(
        cls,
        *,
        suite_id: str,
        branch_id: str,
        idempotency_key: str,
    ) -> Self | None:
        """Первый попавшийся запуск по ключу идемпотентности. Порядка нет. Несколько строк — какая именно, не задано. Нет строки — None. Пустые поля — ValueError."""
        if suite_id == "" or branch_id == "" or idempotency_key == "":
            raise ValueError("suite_id, branch_id and idempotency_key are required")
        return await cls.objects.filter(
            suite_id=suite_id,
            branch_id=branch_id,
            idempotency_key=idempotency_key,
        ).first()

    @classmethod
    async def start_if_queued(
        cls,
        run_id: str,
        *,
        started_at: datetime,
        updated_at: datetime,
    ) -> Self | None:
        if run_id == "":
            raise ValueError("run_id is required")
        updated_rows = await cls.objects.filter(
            company_id=require_active_company().company_id,
            run_id=run_id,
            state=EvaluationRunState.QUEUED,
        ).update(
            returning=False,
            using="flows",
            state=EvaluationRunState.RUNNING,
            started_at=started_at,
            updated_at=updated_at,
        )
        if updated_rows != 1:
            return None
        return await cls.get(run_id)

class EvaluationRunWithCases(StrictBaseModel):
    run: EvaluationRun
    case_runs: list[EvaluationCaseRun]
    gate_result: EvaluationGateResult | None = None

class EvaluationRunComparison(StrictBaseModel):
    left_run: EvaluationRun
    right_run: EvaluationRun
    cases: list[EvaluationCompareCaseDelta]
