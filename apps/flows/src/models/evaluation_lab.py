"""Strict contracts for the first-class flows evaluation lab."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue


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


class EvaluationSuite(StrictBaseModel):
    suite_id: str
    flow_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationRubric(StrictBaseModel):
    rubric_id: str
    flow_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationRubricVersion(StrictBaseModel):
    rubric_version_id: str
    rubric_id: str
    flow_id: str
    version: int
    prompt: str = Field(min_length=1)
    pass_threshold: float = Field(ge=0.0, le=10.0)
    created_at: datetime


class EvaluationRubricWithVersion(StrictBaseModel):
    rubric: EvaluationRubric
    version: EvaluationRubricVersion


class EvaluationCase(StrictBaseModel):
    case_id: str
    suite_id: str
    flow_id: str
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
    created_at: datetime
    updated_at: datetime


class EvaluationSuiteVersion(StrictBaseModel):
    suite_version_id: str
    suite_id: str
    flow_id: str
    flow_config_version: str
    version: int
    suite_snapshot: EvaluationSuite
    cases_snapshot: list[EvaluationCase]
    created_at: datetime


class EvaluationRunSuiteScope(StrictBaseModel):
    type: Literal["suite"]


class EvaluationRunCasesScope(StrictBaseModel):
    type: Literal["cases"]
    case_ids: list[str] = Field(min_length=1)


EvaluationRunScope = Annotated[
    EvaluationRunSuiteScope | EvaluationRunCasesScope,
    Field(discriminator="type"),
]


class EvaluationRun(StrictBaseModel):
    run_id: str
    suite_id: str
    suite_version_id: str
    flow_id: str
    flow_config_version: str
    branch_id: str
    trigger: EvaluationRunTrigger
    scope: EvaluationRunScope
    state: EvaluationRunState
    idempotency_key: str | None = None
    taskiq_task_id: str | None = None
    gate_policy_id: str | None = None
    gate_state: EvaluationGateState | None = None
    total_cases: int
    trials: int = Field(default=1, ge=1)
    max_concurrency: int = Field(default=1, ge=1)
    total_case_runs: int
    passed_case_runs: int = 0
    failed_case_runs: int = 0
    error_case_runs: int = 0
    canceled_case_runs: int = 0
    average_score: float | None = None
    average_duration_ms: float | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    billing_quantity: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationTaskiqExecutionContext(StrictBaseModel):
    task_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    evaluation_run_id: str = Field(min_length=1)


class EvaluationRunJob(StrictBaseModel):
    run_job_id: str
    run_id: str
    taskiq_task_id: str
    state: EvaluationRunJobState
    context_data: JsonObject
    trace_context: JsonObject | None = None
    error: str | None = None
    enqueued_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationDialogMessage(StrictBaseModel):
    role: Literal["user", "assistant", "tester", "judge", "system"]
    content: str


EvaluationScoreValue = float | bool
EvaluationScores = dict[str, EvaluationScoreValue]


class EvaluationCaseRun(StrictBaseModel):
    case_run_id: str
    run_id: str
    case_id: str
    trial_index: int = Field(ge=1)
    suite_id: str
    flow_id: str
    branch_id: str
    state: EvaluationCaseRunState
    task_id: str | None = None
    context_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    billing_quantity: int = Field(default=0, ge=0)
    turns_count: int = Field(default=0, ge=0)
    scores: EvaluationScores | None = None
    total_score: float | None = None
    judge_feedback: str | None = None
    dialog: list[EvaluationDialogMessage] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationRunEvent(StrictBaseModel):
    event_id: str
    run_id: str
    case_run_id: str | None = None
    sequence: int
    event_type: EvaluationEventType
    payload: JsonObject
    created_at: datetime


class EvaluationAnnotation(StrictBaseModel):
    annotation_id: str
    run_id: str
    case_run_id: str | None = None
    case_id: str | None = None
    annotation_type: EvaluationAnnotationType
    comment: str = ""
    payload: JsonObject = Field(default_factory=dict)
    created_by: str
    created_at: datetime
    updated_at: datetime


class EvaluationBaseline(StrictBaseModel):
    baseline_id: str
    suite_id: str
    flow_id: str
    branch_id: str
    run_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class EvaluationGatePolicy(StrictBaseModel):
    gate_policy_id: str
    suite_id: str
    flow_id: str
    branch_id: str
    name: str
    min_pass_rate: float = Field(ge=0.0, le=1.0)
    min_average_score: float | None = Field(default=None, ge=0.0, le=10.0)
    max_failed_case_runs: int = Field(default=0, ge=0)
    max_error_case_runs: int = Field(default=0, ge=0)
    max_average_duration_ms: int | None = Field(default=None, ge=0)
    require_baseline: bool = False
    min_baseline_score_delta: float | None = None
    max_baseline_duration_delta_ms: int | None = Field(default=None, ge=0)
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationGateResult(StrictBaseModel):
    gate_result_id: str
    run_id: str
    gate_policy_id: str
    state: EvaluationGateState
    metrics: JsonObject
    violations: list[str] = Field(default_factory=list)
    created_at: datetime


class EvaluationMonitorFilter(StrictBaseModel):
    user_id: str | None = None
    session_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None


class EvaluationMonitor(StrictBaseModel):
    monitor_id: str
    suite_id: str
    flow_id: str
    branch_id: str
    name: str
    description: str = ""
    state: EvaluationMonitorState
    sampling_rate: float = Field(ge=0.0, le=1.0)
    max_traces_per_sample: int = Field(ge=1, le=500)
    filter: EvaluationMonitorFilter = Field(default_factory=EvaluationMonitorFilter)
    gate_policy_id: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class EvaluationMonitorObservation(StrictBaseModel):
    observation_id: str
    monitor_id: str
    suite_id: str
    flow_id: str
    branch_id: str
    trace_id: str
    task_id: str | None = None
    session_id: str | None = None
    state: EvaluationMonitorObservationState
    span_count: int = Field(ge=0)
    payload: JsonObject
    sampled_at: datetime
    curated_case_id: str | None = None


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


class EvaluationPairwiseJudgment(StrictBaseModel):
    pairwise_judgment_id: str
    suite_id: str
    flow_id: str
    branch_id: str
    left_run_id: str
    right_run_id: str
    left_case_run_id: str
    right_case_run_id: str
    mode: EvaluationPairwiseJudgeMode
    preferred: EvaluationPairwisePreference
    rubric_version_id: str | None = None
    scores: EvaluationScores = Field(default_factory=dict)
    feedback: str = ""
    created_by: str
    created_at: datetime


class EvaluationSuiteCreateRequest(StrictBaseModel):
    flow_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationSuiteUpdateRequest(StrictBaseModel):
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationCaseCreateRequest(StrictBaseModel):
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
    pass


class EvaluationCaseImportRequest(StrictBaseModel):
    format: EvaluationCaseImportFormat
    content: str = Field(min_length=1)


class EvaluationCaseImportResult(StrictBaseModel):
    cases: list[EvaluationCase]


class EvaluationDialogCaseCreateRequest(StrictBaseModel):
    name: str
    description: str = ""
    branch_ids: Literal["*"] | list[str]
    dialog: list[EvaluationDialogMessage] = Field(min_length=1)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationTraceCaseCreateRequest(StrictBaseModel):
    name: str
    description: str = ""
    trace_id: str = Field(min_length=1)
    branch_ids: Literal["*"] | list[str]
    dialog: list[EvaluationDialogMessage] = Field(min_length=1)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class EvaluationMonitorObservationCaseCreateRequest(StrictBaseModel):
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
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class EvaluationRubricVersionCreateRequest(StrictBaseModel):
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
    trigger: EvaluationRunTrigger
    trials: int = Field(default=1, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=50)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class EvaluationBaselineSetRequest(StrictBaseModel):
    run_id: str


class EvaluationGatePolicyCreateRequest(StrictBaseModel):
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
    pass


class EvaluationAnnotationCreateRequest(StrictBaseModel):
    case_run_id: str | None = None
    case_id: str | None = None
    annotation_type: EvaluationAnnotationType
    comment: str = ""
    payload: JsonObject = Field(default_factory=dict)


class EvaluationAnnotationUpdateRequest(StrictBaseModel):
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
    branch_id: str
    name: str
    description: str = ""
    state: EvaluationMonitorState
    sampling_rate: float = Field(ge=0.0, le=1.0)
    max_traces_per_sample: int = Field(ge=1, le=500)
    filter: EvaluationMonitorFilter = Field(default_factory=EvaluationMonitorFilter)
    gate_policy_id: str | None = None


class EvaluationMonitorSampleRequest(StrictBaseModel):
    limit: int = Field(default=100, ge=1, le=500)


class EvaluationMonitorSampleResult(StrictBaseModel):
    monitor: EvaluationMonitor
    observations: list[EvaluationMonitorObservation]


class EvaluationMonitorCycleRequest(StrictBaseModel):
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
