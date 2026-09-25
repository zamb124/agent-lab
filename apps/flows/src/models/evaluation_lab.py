"""Строгие контракты first-class evaluation lab для flows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index, Q, atomic
from oxyde.exceptions import IntegrityError
from pydantic import Field, SerializationInfo, field_serializer, model_validator

from core.context import require_active_company
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject, JsonValue


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class EvaluationRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELED = "canceled"


class EvaluationCaseRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELED = "canceled"


class EvaluationEventType(StrEnum):
    RUN_CREATED = "run_created"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    RUN_CANCELED = "run_canceled"
    GATE_EVALUATED = "gate_evaluated"
    CASE_STARTED = "case_started"
    CASE_FINISHED = "case_finished"
    CASE_FAILED = "case_failed"
    CASE_CANCELED = "case_canceled"
    TURN_STARTED = "turn_started"
    MESSAGE_RECORDED = "message_recorded"
    CHECK_STARTED = "check_started"
    SCORE_RECORDED = "score_recorded"


class EvaluationRunTrigger(StrEnum):
    MANUAL = "manual"
    CI = "ci"
    NIGHTLY = "nightly"
    API = "api"


class EvaluationAnnotationType(StrEnum):
    COMMENT = "comment"
    APPROVAL = "approval"
    REJECTION = "rejection"
    ISSUE = "issue"


class EvaluationCaseImportFormat(StrEnum):
    JSONL = "jsonl"
    CSV = "csv"


class EvaluationGateState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class EvaluationRunJobState(StrEnum):
    PENDING = "pending"
    ENQUEUED = "enqueued"
    FAILED = "failed"


class EvaluationMonitorState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class EvaluationMonitorObservationState(StrEnum):
    SAMPLED = "sampled"
    CURATED = "curated"


class EvaluationBuiltinEvaluatorCategory(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM_JUDGE = "llm_judge"
    SAFETY = "safety"
    RETRIEVAL = "retrieval"
    TRACE = "trace"
    PAIRWISE = "pairwise"


class EvaluationBuiltinMetricId(StrEnum):
    ROUGE_L = "rouge_l"
    BLEU = "bleu"
    TOXICITY = "toxicity"
    SAFETY = "safety"
    GROUNDEDNESS = "groundedness"
    ANSWER_RELEVANCE = "answer_relevance"
    TOOL_ACCURACY = "tool_accuracy"


class EvaluationPairwiseJudgeMode(StrEnum):
    HUMAN = "human"
    LLM = "llm"


class EvaluationPairwisePreference(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TIE = "tie"


class EvaluationInputText(StrictBaseModel):
    type: Literal["text"]
    content: str = Field(min_length=1)


class EvaluationInputInlineCode(StrictBaseModel):
    type: Literal["inline_code"]
    language: Literal["python", "javascript", "typescript", "go", "csharp"]
    source: str = Field(min_length=1)
    entrypoint: str | None = None


class EvaluationInputNode(StrictBaseModel):
    type: Literal["node"]
    node_id: str | None = None
    node: JsonObject | None = None


EvaluationInput = Annotated[
    EvaluationInputText | EvaluationInputInlineCode | EvaluationInputNode,
    Field(discriminator="type"),
]


class EvaluationCheckSource(StrEnum):
    RESPONSE = "response"
    STATE = "state"


class EvaluationContainsMode(StrEnum):
    ANY = "any"
    ALL = "all"


class EvaluationCheckContains(StrictBaseModel):
    type: Literal["contains"]
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    values: list[str] = Field(min_length=1)
    mode: EvaluationContainsMode = EvaluationContainsMode.ANY
    case_sensitive: bool = False
    state_path: str | None = None


class EvaluationCheckNotContains(StrictBaseModel):
    type: Literal["not_contains"]
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    values: list[str] = Field(min_length=1)
    case_sensitive: bool = False
    state_path: str | None = None


class EvaluationCheckRegex(StrictBaseModel):
    type: Literal["regex"]
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    pattern: str = Field(min_length=1)
    ignore_case: bool = True
    state_path: str | None = None


class EvaluationCheckLength(StrictBaseModel):
    type: Literal["length"]
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    min_chars: int | None = Field(default=None, ge=0)
    max_chars: int | None = Field(default=None, ge=0)
    state_path: str | None = None


class EvaluationStateOperator(StrEnum):
    EXISTS = "exists"
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class EvaluationCheckStatePath(StrictBaseModel):
    type: Literal["state_path"]
    path: str = Field(min_length=1)
    operator: EvaluationStateOperator
    value: JsonValue = None


class EvaluationCheckJsonSchema(StrictBaseModel):
    type: Literal["json_schema"]
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    json_schema: JsonObject
    state_path: str | None = None


class EvaluationTraceAssertion(StrEnum):
    TOOL_CALLED = "tool_called"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"


class EvaluationCheckTraceAssertion(StrictBaseModel):
    type: Literal["trace_assertion"]
    assertion: EvaluationTraceAssertion
    value: str = Field(min_length=1)


class EvaluationCheckCode(StrictBaseModel):
    type: Literal["code"]
    language: Literal["python", "javascript", "typescript", "go", "csharp"]
    source: str = Field(min_length=1)
    entrypoint: str | None = None


class EvaluationCheckLlmJudge(StrictBaseModel):
    type: Literal["llm_judge"]
    rubric_version_id: str = Field(min_length=1)
    judge_node_id: str | None = None
    judge_node: JsonObject | None = None


class EvaluationCheckBuiltinMetric(StrictBaseModel):
    type: Literal["builtin_metric"]
    evaluator_id: EvaluationBuiltinMetricId
    source: EvaluationCheckSource = EvaluationCheckSource.RESPONSE
    state_path: str | None = None
    reference: str | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=10.0)
    judge_node_id: str | None = None
    judge_node: JsonObject | None = None


EvaluationCheck = Annotated[
    EvaluationCheckContains
    | EvaluationCheckNotContains
    | EvaluationCheckRegex
    | EvaluationCheckLength
    | EvaluationCheckStatePath
    | EvaluationCheckJsonSchema
    | EvaluationCheckTraceAssertion
    | EvaluationCheckCode
    | EvaluationCheckLlmJudge
    | EvaluationCheckBuiltinMetric,
    Field(discriminator="type"),
]


class EvaluationTurn(StrictBaseModel):
    input: EvaluationInput
    checks: list[EvaluationCheck] = Field(default_factory=list)


class EvaluationTargetFlow(StrictBaseModel):
    type: Literal["flow"]
    flow_id: str | None = None
    branch_id: str | None = None


class EvaluationTargetNode(StrictBaseModel):
    type: Literal["node"]
    node: JsonObject


EvaluationTarget = Annotated[
    EvaluationTargetFlow | EvaluationTargetNode,
    Field(discriminator="type"),
]


class EvaluationSuite(CompanyScopedModel):
    """Набор кейсов evaluation. Таблица ``evaluation_suites``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_suites"
        unique_together: list[tuple[str, str, str]] = [("company_id", "flow_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "flow_id"]),
        ]

    suite_id: str = DbField(db_pk=True)
    flow_id: str = DbField()
    name: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    archived_at: datetime | None = DbField(default=None)

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)
        if self.archived_at is not None:
            self.archived_at = _as_utc(self.archived_at)
        return self

    @classmethod
    async def list_for_flow(cls, flow_id: str) -> list[Self]:
        if flow_id == "":
            raise ValueError("flow_id is required")
        return await cls.objects.filter(flow_id=flow_id).order_by("-updated_at", "suite_id").all()


class EvaluationRubric(CompanyScopedModel):
    """Метаданные LLM-судьи. Таблица ``evaluation_rubrics``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_rubrics"
        unique_together: list[tuple[str, str, str]] = [("company_id", "flow_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "flow_id"]),
        ]

    rubric_id: str = DbField(db_pk=True)
    flow_id: str = DbField()
    name: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    archived_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_for_flow(cls, flow_id: str) -> list[Self]:
        if flow_id == "":
            raise ValueError("flow_id is required")
        return await cls.objects.filter(flow_id=flow_id).order_by("-updated_at", "rubric_id").all()

    @classmethod
    async def create_with_first_version(
        cls,
        rubric: Self,
        version: EvaluationRubricVersion,
    ) -> None:
        async with atomic(using="flows"):
            _ = await cls.set(rubric)
            _ = await EvaluationRubricVersion.set(version)


class EvaluationRubricVersion(CompanyScopedModel):
    """Неизменяемый промпт рубрики. Таблица ``evaluation_rubric_versions``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_rubric_versions"
        unique_together: list[tuple[str, str, str]] = [("company_id", "rubric_id", "version")]
        indexes: list[Index] = [
            Index(["company_id", "rubric_id"]),
        ]

    rubric_version_id: str = DbField(db_pk=True)
    rubric_id: str = DbField()
    flow_id: str = DbField()
    version: int = DbField()
    prompt: str = DbField(min_length=1, db_type="TEXT")
    pass_threshold: float = DbField(ge=0.0, le=10.0)
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)

    @classmethod
    async def list_for_rubric(cls, rubric_id: str) -> list[Self]:
        if rubric_id == "":
            raise ValueError("rubric_id is required")
        return await cls.objects.filter(rubric_id=rubric_id).order_by("-version").all()

    @classmethod
    async def next_version(cls, rubric_id: str) -> int:
        if rubric_id == "":
            raise ValueError("rubric_id is required")
        latest = await cls.objects.filter(rubric_id=rubric_id).order_by("-version").first()
        if latest is None:
            return 1
        return latest.version + 1


class EvaluationRubricWithVersion(StrictBaseModel):
    rubric: EvaluationRubric
    version: EvaluationRubricVersion


class EvaluationCase(CompanyScopedModel):
    """Кейс набора evaluation. Таблица ``evaluation_cases``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_cases"
        unique_together: list[tuple[str, str, str]] = [("company_id", "suite_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
            Index(["company_id", "flow_id"]),
        ]

    case_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    name: str = DbField()
    branch_ids: Literal["*"] | list[str] = DbField(db_type="JSONB")
    turns: list[EvaluationTurn] = DbField(min_length=1, db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    target: EvaluationTargetFlow | EvaluationTargetNode = DbField(
        default_factory=lambda: EvaluationTargetFlow(type="flow"),
        db_type="JSONB",
        discriminator="type",
    )
    initial_state: JsonObject | None = DbField(default=None, db_type="JSONB")
    max_turns: int = DbField(default=10, ge=1, le=200)
    timeout_seconds: int = DbField(default=300, ge=1, le=3600)
    enabled: bool = DbField(default=True)
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    sort_order: int = DbField(default=0)

    @field_serializer("branch_ids")
    def serialize_branch_ids(
        self,
        value: Literal["*"] | list[str],
        info: SerializationInfo,
    ) -> str | list[str]:
        # Oxyde кладёт строку в jsonb только если она сама является JSON.
        if info.mode == "python" and isinstance(value, str):
            return json.dumps(value)
        return value

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        self.created_at = _as_utc(self.created_at)
        self.updated_at = _as_utc(self.updated_at)
        return self

    @classmethod
    async def list_for_suite(cls, suite_id: str) -> list[Self]:
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await (
            cls.objects.filter(suite_id=suite_id)
            .order_by("sort_order", "created_at", "case_id")
            .all()
        )


class EvaluationSuiteVersion(CompanyScopedModel):
    """Неизменяемый снимок набора и кейсов. Таблица ``evaluation_suite_versions``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_suite_versions"
        unique_together: list[tuple[str, str, str]] = [("company_id", "suite_id", "version")]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
        ]

    suite_version_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    flow_config_version: str = DbField()
    version: int = DbField()
    suite_snapshot: JsonObject = DbField(db_type="JSONB")
    cases_snapshot: list[JsonObject] = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)

    @classmethod
    async def next_version(cls, suite_id: str) -> int:
        if suite_id == "":
            raise ValueError("suite_id is required")
        latest = await cls.objects.filter(suite_id=suite_id).order_by("-version").first()
        if latest is None:
            return 1
        return latest.version + 1


class EvaluationRunSuiteScope(StrictBaseModel):
    type: Literal["suite"]


class EvaluationRunCasesScope(StrictBaseModel):
    type: Literal["cases"]
    case_ids: list[str] = Field(min_length=1)


EvaluationRunScope = Annotated[
    EvaluationRunSuiteScope | EvaluationRunCasesScope,
    Field(discriminator="type"),
]


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
    async def list_for_suite(cls, suite_id: str, limit: int) -> list[Self]:
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
    async def for_idempotency(
        cls,
        *,
        suite_id: str,
        branch_id: str,
        idempotency_key: str,
    ) -> Self | None:
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


class EvaluationTaskiqExecutionContext(StrictBaseModel):
    task_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    evaluation_run_id: str = Field(min_length=1)


class EvaluationRunJob(CompanyScopedModel):
    """Очередь запуска прогона. Таблица ``evaluation_run_jobs``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_run_jobs"
        unique_together: list[tuple[str, str]] = [
            ("company_id", "run_id"),
            ("company_id", "taskiq_task_id"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "state", "created_at"]),
        ]

    run_job_id: str = DbField(db_pk=True)
    run_id: str = DbField()
    taskiq_task_id: str = DbField()
    state: EvaluationRunJobState = DbField()
    context_data: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    trace_context: JsonObject | None = DbField(default=None, db_type="JSONB")
    error: str | None = DbField(default=None, db_type="TEXT")
    enqueued_at: datetime | None = DbField(default=None)

    @classmethod
    async def for_run(cls, run_id: str) -> Self | None:
        if run_id == "":
            raise ValueError("run_id is required")
        return await cls.objects.filter(run_id=run_id).first()

    @classmethod
    async def list_pending(cls, limit: int) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be positive")
        return await (
            cls.objects.filter(state=EvaluationRunJobState.PENDING)
            .order_by("created_at", "run_job_id")
            .limit(limit)
            .all()
        )

    @classmethod
    async def insert_for_run(cls, job: Self) -> Self:
        if job.run_id == "":
            raise ValueError("run_id is required")
        existing = await cls.for_run(job.run_id)
        if existing is not None:
            return existing
        try:
            _ = await cls.set(job)
        except IntegrityError:
            stored = await cls.for_run(job.run_id)
            if stored is None:
                raise
            return stored
        return job


class EvaluationDialogMessage(StrictBaseModel):
    role: Literal["user", "assistant", "tester", "judge", "system"]
    content: str


EvaluationScoreValue = float | bool
EvaluationScores = dict[str, EvaluationScoreValue]


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


class EvaluationAnnotation(CompanyScopedModel):
    """Заметка к прогону evaluation. Таблица ``evaluation_annotations``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_annotations"
        indexes: list[Index] = [
            Index(["company_id", "run_id"]),
            Index(["company_id", "case_run_id"]),
        ]

    annotation_id: str = DbField(db_pk=True)
    run_id: str = DbField(db_index=True)
    annotation_type: EvaluationAnnotationType = DbField()
    created_by: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    case_run_id: str | None = DbField(default=None)
    case_id: str | None = DbField(default=None)
    comment: str = DbField(default="")
    payload: JsonObject = DbField(default_factory=dict, db_type="JSONB")

    @classmethod
    async def list_for_run(cls, run_id: str) -> list[Self]:
        if run_id == "":
            raise ValueError("run_id is required")
        return await (
            cls.objects.filter(run_id=run_id)
            .order_by("created_at", "annotation_id")
            .all()
        )


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
    async def list_for_suite(cls, suite_id: str) -> list[Self]:
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


class EvaluationMonitorFilter(StrictBaseModel):
    user_id: str | None = None
    session_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None


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
    async def list_for_suite(cls, suite_id: str) -> list[Self]:
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await (
            cls.objects.filter(suite_id=suite_id).order_by("-updated_at", "monitor_id").all()
        )

    @classmethod
    async def list_active(cls, limit: int) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return await (
            cls.objects.filter(state=EvaluationMonitorState.ACTIVE)
            .order_by("updated_at", "monitor_id")
            .limit(limit)
            .all()
        )


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
    async def list_for_monitor(cls, monitor_id: str, limit: int) -> list[Self]:
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


class EvaluationBuiltinEvaluator(StrictBaseModel):
    evaluator_id: EvaluationBuiltinMetricId | Literal[
        "contains",
        "not_contains",
        "regex",
        "length",
        "json_schema",
        "trace_assertion",
        "code",
        "llm_judge",
        "pairwise_llm",
        "pairwise_human",
    ]
    name: str
    category: EvaluationBuiltinEvaluatorCategory
    description: str
    check_type: str
    score_min: float = Field(ge=0.0)
    score_max: float = Field(ge=0.0)
    default_threshold: float | None = Field(default=None, ge=0.0, le=10.0)
    requires_reference: bool
    requires_llm: bool
    supports_pairwise: bool


class EvaluationBuiltinEvaluatorCatalog(StrictBaseModel):
    items: list[EvaluationBuiltinEvaluator]


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


class EvaluationSuiteCreateRequest(StrictBaseModel):
    flow_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationSuiteUpdateRequest(StrictBaseModel):
    suite_id: str = ""
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationCaseCreateRequest(StrictBaseModel):
    suite_id: str = ""
    name: str
    description: str = ""
    branch_ids: Literal["*"] | list[str]
    target: EvaluationTarget = Field(default_factory=lambda: EvaluationTargetFlow(type="flow"))
    initial_state: JsonObject | None = None
    turns: list[EvaluationTurn] = Field(min_length=1)
    max_turns: int = Field(default=10, ge=1, le=200)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationCaseUpdateRequest(EvaluationCaseCreateRequest):
    case_id: str = ""


class EvaluationCaseImportRequest(StrictBaseModel):
    suite_id: str = ""
    format: EvaluationCaseImportFormat
    content: str = Field(min_length=1)


class EvaluationCaseImportResult(StrictBaseModel):
    cases: list[EvaluationCase]


class EvaluationDialogCaseCreateRequest(StrictBaseModel):
    suite_id: str = ""
    name: str
    description: str = ""
    branch_ids: Literal["*"] | list[str]
    dialog: list[EvaluationDialogMessage] = Field(min_length=1)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationTraceCaseCreateRequest(StrictBaseModel):
    suite_id: str = ""
    name: str
    description: str = ""
    trace_id: str = Field(min_length=1)
    branch_ids: Literal["*"] | list[str]
    dialog: list[EvaluationDialogMessage] = Field(min_length=1)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationMonitorObservationCaseCreateRequest(StrictBaseModel):
    monitor_id: str = ""
    trace_id: str = ""
    name: str
    description: str = ""
    dialog: list[EvaluationDialogMessage] = Field(min_length=1)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationMonitorObservationCurationResult(StrictBaseModel):
    case: EvaluationCase
    observation: EvaluationMonitorObservation


class EvaluationCaseRunCaseCreateRequest(StrictBaseModel):
    suite_id: str = ""
    name: str
    description: str = ""
    case_run_id: str
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationRubricCreateRequest(StrictBaseModel):
    flow_id: str
    name: str
    prompt: str = Field(min_length=1)
    pass_threshold: float = Field(ge=0.0, le=10.0)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationRubricUpdateRequest(StrictBaseModel):
    rubric_id: str = ""
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationRubricVersionCreateRequest(StrictBaseModel):
    rubric_id: str = ""
    prompt: str = Field(min_length=1)
    pass_threshold: float = Field(ge=0.0, le=10.0)


class EvaluationRunCreateRequest(StrictBaseModel):
    suite_id: str
    branch_id: str
    trigger: EvaluationRunTrigger = EvaluationRunTrigger.MANUAL
    scope: EvaluationRunScope
    trials: int = Field(default=1, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=50)
    gate_policy_id: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class EvaluationGatePolicyRunRequest(StrictBaseModel):
    gate_policy_id: str = ""
    trigger: EvaluationRunTrigger
    trials: int = Field(default=1, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=50)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class EvaluationBaselineSetRequest(StrictBaseModel):
    suite_id: str = ""
    branch_id: str = ""
    run_id: str


class EvaluationGatePolicyCreateRequest(StrictBaseModel):
    suite_id: str = ""
    branch_id: str
    name: str
    min_pass_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    min_average_score: float | None = Field(default=None, ge=0.0, le=10.0)
    max_failed_case_runs: int = Field(default=0, ge=0)
    max_error_case_runs: int = Field(default=0, ge=0)
    max_average_duration_ms: int | None = Field(default=None, ge=0)
    require_baseline: bool = False
    min_baseline_score_delta: float | None = None
    max_baseline_duration_delta_ms: int | None = Field(default=None, ge=0)


class EvaluationGatePolicyUpdateRequest(EvaluationGatePolicyCreateRequest):
    gate_policy_id: str = ""


class EvaluationAnnotationCreateRequest(StrictBaseModel):
    run_id: str = ""
    case_run_id: str | None = None
    case_id: str | None = None
    annotation_type: EvaluationAnnotationType
    comment: str = ""
    payload: JsonObject = Field(default_factory=dict)


class EvaluationAnnotationUpdateRequest(StrictBaseModel):
    annotation_id: str = ""
    annotation_type: EvaluationAnnotationType
    comment: str = ""
    payload: JsonObject = Field(default_factory=dict)


class EvaluationMonitorCreateRequest(StrictBaseModel):
    suite_id: str
    branch_id: str
    name: str
    description: str = ""
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    max_traces_per_sample: int = Field(default=100, ge=1, le=500)
    filter: EvaluationMonitorFilter = Field(default_factory=EvaluationMonitorFilter)
    gate_policy_id: str | None = None


class EvaluationMonitorUpdateRequest(StrictBaseModel):
    monitor_id: str = ""
    branch_id: str
    name: str
    description: str = ""
    state: EvaluationMonitorState
    sampling_rate: float = Field(ge=0.0, le=1.0)
    max_traces_per_sample: int = Field(ge=1, le=500)
    filter: EvaluationMonitorFilter = Field(default_factory=EvaluationMonitorFilter)
    gate_policy_id: str | None = None


class EvaluationMonitorSampleRequest(StrictBaseModel):
    monitor_id: str = ""
    limit: int = Field(default=100, ge=1, le=500)


class EvaluationMonitorSampleResult(StrictBaseModel):
    monitor: EvaluationMonitor
    observations: list[EvaluationMonitorObservation]


class EvaluationMonitorCycleRequest(StrictBaseModel):
    monitor_id: str = ""
    limit: int = Field(default=100, ge=1, le=500)
    enqueue_gate_run: bool = True
    trials: int = Field(default=1, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=50)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class EvaluationMonitorCycleResult(StrictBaseModel):
    monitor: EvaluationMonitor
    observations: list[EvaluationMonitorObservation]
    run: EvaluationRun | None = None


class EvaluationActiveMonitorCyclesRequest(StrictBaseModel):
    limit_per_monitor: int = Field(default=100, ge=1, le=500)
    enqueue_gate_runs: bool = True
    trials: int = Field(default=1, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=50)


class EvaluationActiveMonitorCyclesResult(StrictBaseModel):
    cycles: list[EvaluationMonitorCycleResult]


class EvaluationPendingRunJobsEnqueueResult(StrictBaseModel):
    enqueued_run_ids: list[str]
    failed_run_ids: list[str]


class EvaluationPairwiseJudgeRequest(StrictBaseModel):
    mode: EvaluationPairwiseJudgeMode
    left_case_run_id: str = Field(min_length=1)
    right_case_run_id: str = Field(min_length=1)
    preferred: EvaluationPairwisePreference | None = None
    rubric_version_id: str | None = None
    scores: EvaluationScores = Field(default_factory=dict)
    feedback: str = ""
    judge_node_id: str | None = None
    judge_node: JsonObject | None = None


class EvaluationRunWithCases(StrictBaseModel):
    run: EvaluationRun
    case_runs: list[EvaluationCaseRun]
    gate_result: EvaluationGateResult | None = None


class EvaluationCompareCaseDelta(StrictBaseModel):
    case_id: str
    trial_index: int
    left: EvaluationCaseRun | None
    right: EvaluationCaseRun | None
    score_delta: float | None
    duration_delta_ms: int | None


class EvaluationRunComparison(StrictBaseModel):
    left_run: EvaluationRun
    right_run: EvaluationRun
    cases: list[EvaluationCompareCaseDelta]


class EvaluationBaselineComparison(StrictBaseModel):
    baseline: EvaluationBaseline
    comparison: EvaluationRunComparison


class EvaluationMatrixCase(StrictBaseModel):
    case_id: str
    name: str
    enabled: bool
    tags: list[str] = Field(default_factory=list)
    sort_order: int


class EvaluationMatrixRun(StrictBaseModel):
    run_id: str
    state: EvaluationRunState
    gate_state: EvaluationGateState | None = None
    total_case_runs: int
    passed_case_runs: int
    failed_case_runs: int
    error_case_runs: int
    canceled_case_runs: int
    average_score: float | None = None
    average_duration_ms: float | None = None
    billing_quantity: int = Field(ge=0)
    created_at: datetime
    finished_at: datetime | None = None


class EvaluationMatrixCell(StrictBaseModel):
    run_id: str
    case_id: str
    trial_index: int = Field(ge=1)
    state: EvaluationCaseRunState
    total_score: float | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    billing_quantity: int = Field(ge=0)
    case_run_id: str


class EvaluationResultsMatrix(StrictBaseModel):
    suite_id: str
    branch_id: str
    cases: list[EvaluationMatrixCase]
    runs: list[EvaluationMatrixRun]
    cells: list[EvaluationMatrixCell]


class EvaluationRunEventsPage(StrictBaseModel):
    items: list[EvaluationRunEvent]
    next_sequence: int | None = None
    has_more: bool


class EvaluationTraceSpan(StrictBaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    operation_name: str
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None
    status: str | None = None
    service_name: str
    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    attributes: JsonObject = Field(default_factory=dict)


class EvaluationTraceWorkflowEvent(StrictBaseModel):
    sequence: int
    event_type: str
    payload: JsonObject
    state_delta: JsonObject
    created_at: str


class EvaluationTraceNodeStep(StrictBaseModel):
    sequence: int
    node_id: str
    node_type: str | None = None
    status: Literal["scheduled", "completed", "failed"]
    state_delta: JsonObject | None = None


class EvaluationTraceToolCall(StrictBaseModel):
    sequence: int
    activity_id: str
    activity_type: str
    activity_status: str
    node_id: str | None = None
    tool_call_id: str | None = None
    attempt: int
    error: str | None = None


class EvaluationTraceStateDiff(StrictBaseModel):
    sequence: int
    node_id: str
    node_type: str | None = None
    state_delta: JsonObject


class EvaluationCaseRunTrace(StrictBaseModel):
    case_run: EvaluationCaseRun
    spans: list[EvaluationTraceSpan]
    workflow_events: list[EvaluationTraceWorkflowEvent]
    node_steps: list[EvaluationTraceNodeStep]
    tool_calls: list[EvaluationTraceToolCall]
    state_diffs: list[EvaluationTraceStateDiff]


class EvaluationFlowIdPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)


class EvaluationSuiteIdPayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)


class EvaluationSuiteCaseIdPayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)


class EvaluationRunIdPayload(StrictBaseModel):
    run_id: str = Field(min_length=1)


class EvaluationRunsListPayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)


class EvaluationEventsPagePayload(StrictBaseModel):
    run_id: str = Field(min_length=1)
    after_sequence: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=500)


class EvaluationCompareRunsPayload(StrictBaseModel):
    left_run_id: str = Field(min_length=1)
    right_run_id: str = Field(min_length=1)


class EvaluationMatrixPayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=100)


class EvaluationCaseRunIdPayload(StrictBaseModel):
    case_run_id: str = Field(min_length=1)


class EvaluationRubricIdPayload(StrictBaseModel):
    rubric_id: str = Field(min_length=1)


class EvaluationAnnotationIdPayload(StrictBaseModel):
    annotation_id: str = Field(min_length=1)


class EvaluationMonitorIdPayload(StrictBaseModel):
    monitor_id: str = Field(min_length=1)


class EvaluationMonitorObservationsPayload(StrictBaseModel):
    monitor_id: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=500)


class EvaluationPendingJobsPayload(StrictBaseModel):
    limit: int = Field(default=50, ge=1, le=100)


class EvaluationGatePolicyIdPayload(StrictBaseModel):
    gate_policy_id: str = Field(min_length=1)


class EvaluationBaselineItemPayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)


class EvaluationBaselineComparePayload(StrictBaseModel):
    suite_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)


class EvaluationDeletedResponse(StrictBaseModel):
    deleted: Literal[True] = True
