"""First-class evaluation lab service."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import re
import time
import uuid
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import Field

import core.tracing.attributes as trace_attributes
from apps.flows.src.db import EvaluationLabRepository, FlowRepository, NodeRepository
from apps.flows.src.durable_execution import (
    ActivityLifecyclePayload,
    NodeCompletedPayload,
    NodeFailedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    RunStartedPayload,
    SuperstepStartedPayload,
    WorkflowEventRecord,
    WorkflowEventType,
    build_state_delta,
    workflow_event_payload_json,
)
from apps.flows.src.models.evaluation_lab import (
    EvaluationAnnotation,
    EvaluationAnnotationCreateRequest,
    EvaluationAnnotationUpdateRequest,
    EvaluationBaseline,
    EvaluationBaselineComparison,
    EvaluationBaselineSetRequest,
    EvaluationBuiltinEvaluator,
    EvaluationBuiltinEvaluatorCatalog,
    EvaluationBuiltinEvaluatorCategory,
    EvaluationBuiltinMetricId,
    EvaluationCase,
    EvaluationCaseCreateRequest,
    EvaluationCaseImportFormat,
    EvaluationCaseImportRequest,
    EvaluationCaseImportResult,
    EvaluationCaseRun,
    EvaluationCaseRunCaseCreateRequest,
    EvaluationCaseRunState,
    EvaluationCaseRunTrace,
    EvaluationCaseUpdateRequest,
    EvaluationCheck,
    EvaluationCheckBuiltinMetric,
    EvaluationCheckCode,
    EvaluationCheckContains,
    EvaluationCheckJsonSchema,
    EvaluationCheckLength,
    EvaluationCheckLlmJudge,
    EvaluationCheckNotContains,
    EvaluationCheckRegex,
    EvaluationCheckSource,
    EvaluationCheckStatePath,
    EvaluationCheckTraceAssertion,
    EvaluationCompareCaseDelta,
    EvaluationContainsMode,
    EvaluationDialogCaseCreateRequest,
    EvaluationDialogMessage,
    EvaluationEventType,
    EvaluationGatePolicy,
    EvaluationGatePolicyCreateRequest,
    EvaluationGatePolicyRunRequest,
    EvaluationGatePolicyUpdateRequest,
    EvaluationGateResult,
    EvaluationGateState,
    EvaluationInput,
    EvaluationInputInlineCode,
    EvaluationInputNode,
    EvaluationInputText,
    EvaluationMatrixCase,
    EvaluationMatrixCell,
    EvaluationMatrixRun,
    EvaluationMonitor,
    EvaluationMonitorCreateRequest,
    EvaluationMonitorCycleRequest,
    EvaluationMonitorCycleResult,
    EvaluationMonitorObservation,
    EvaluationMonitorObservationCaseCreateRequest,
    EvaluationMonitorObservationCurationResult,
    EvaluationMonitorObservationState,
    EvaluationMonitorSampleRequest,
    EvaluationMonitorSampleResult,
    EvaluationMonitorState,
    EvaluationMonitorUpdateRequest,
    EvaluationPairwiseJudgeMode,
    EvaluationPairwiseJudgeRequest,
    EvaluationPairwiseJudgment,
    EvaluationPairwisePreference,
    EvaluationResultsMatrix,
    EvaluationRubric,
    EvaluationRubricCreateRequest,
    EvaluationRubricUpdateRequest,
    EvaluationRubricVersion,
    EvaluationRubricVersionCreateRequest,
    EvaluationRun,
    EvaluationRunComparison,
    EvaluationRunCreateRequest,
    EvaluationRunEvent,
    EvaluationRunEventsPage,
    EvaluationRunJob,
    EvaluationRunJobState,
    EvaluationRunScope,
    EvaluationRunState,
    EvaluationRunSuiteScope,
    EvaluationRunTrigger,
    EvaluationRunWithCases,
    EvaluationScores,
    EvaluationStateOperator,
    EvaluationSuite,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteUpdateRequest,
    EvaluationSuiteVersion,
    EvaluationTargetFlow,
    EvaluationTaskiqExecutionContext,
    EvaluationTraceAssertion,
    EvaluationTraceCaseCreateRequest,
    EvaluationTraceNodeStep,
    EvaluationTraceSpan,
    EvaluationTraceStateDiff,
    EvaluationTraceToolCall,
    EvaluationTraceWorkflowEvent,
    EvaluationTurn,
)
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.registry.nodes import NodeRegistry
from apps.flows.src.services.flow_factory import FlowFactory
from apps.flows.src.tasks.task_names import TASK_EXECUTE_EVALUATION_RUN
from core.ai.resolver import COST_ORIGIN_COMPANY, AICapability, resolve_llm_for_capability
from core.ai.runtime import create_llm_client
from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.context import get_context, require_active_company
from core.llm_context import LLMContextPatch
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.billing_models import UsageType
from core.state import ExecutionState
from core.tracing.context import get_current_trace_context
from core.tracing.models import TraceSearchResult, TraceSpanRecord
from core.tracing.operation_span import traced_operation
from core.tracing.repository import SpanRepository
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_array,
    parse_json_object,
    require_json_array,
    require_json_object,
)
from core.ui_events.dispatcher import publish_ui_event_to_company

logger = get_logger(__name__)

FLOWS_EVALUATION_EVENT_RECORDED = "flows/evaluation/event"
EVALUATION_JUDGE_TOOL_NAME = "record_evaluation_judgment"
EVALUATION_BUILTIN_METRIC_TOOL_NAME = "record_evaluation_builtin_metric"
EVALUATION_PAIRWISE_TOOL_NAME = "record_evaluation_pairwise_judgment"

LLM_BUILTIN_METRIC_IDS = {
    EvaluationBuiltinMetricId.TOXICITY,
    EvaluationBuiltinMetricId.SAFETY,
    EvaluationBuiltinMetricId.GROUNDEDNESS,
    EvaluationBuiltinMetricId.ANSWER_RELEVANCE,
    EvaluationBuiltinMetricId.TOOL_ACCURACY,
}

REFERENCE_BUILTIN_METRIC_IDS = {
    EvaluationBuiltinMetricId.ROUGE_L,
    EvaluationBuiltinMetricId.BLEU,
    EvaluationBuiltinMetricId.GROUNDEDNESS,
    EvaluationBuiltinMetricId.ANSWER_RELEVANCE,
    EvaluationBuiltinMetricId.TOOL_ACCURACY,
}

BUILTIN_METRIC_DEFAULT_THRESHOLDS: dict[EvaluationBuiltinMetricId, float] = {
    EvaluationBuiltinMetricId.ROUGE_L: 7.0,
    EvaluationBuiltinMetricId.BLEU: 5.0,
    EvaluationBuiltinMetricId.TOXICITY: 8.0,
    EvaluationBuiltinMetricId.SAFETY: 8.0,
    EvaluationBuiltinMetricId.GROUNDEDNESS: 7.0,
    EvaluationBuiltinMetricId.ANSWER_RELEVANCE: 7.0,
    EvaluationBuiltinMetricId.TOOL_ACCURACY: 7.0,
}

TargetCallable = Callable[[ExecutionState], Awaitable[ExecutionState]]


class EvaluationLabNotFoundError(ValueError):
    """Requested evaluation lab object does not exist."""


class EvaluationLabValidationError(ValueError):
    """Evaluation lab request is structurally valid but cannot be executed."""


class EvaluationLlmJudgeResult(StrictBaseModel):
    scores: EvaluationScores = Field(default_factory=dict)
    total_score: float | None = Field(default=None, ge=0.0, le=10.0)
    passed: bool | None = None
    feedback: str | None = None


class EvaluationBuiltinMetricJudgeResult(StrictBaseModel):
    score: float = Field(ge=0.0, le=10.0)
    passed: bool
    feedback: str | None = None


class EvaluationPairwiseLlmJudgeResult(StrictBaseModel):
    preferred: EvaluationPairwisePreference
    scores: EvaluationScores = Field(default_factory=dict)
    feedback: str = ""


@dataclass(frozen=True)
class CheckOutcome:
    scores: EvaluationScores
    passed: bool
    feedback: str | None = None


@dataclass(frozen=True)
class TargetRuntime:
    callable: TargetCallable
    flow_id: str
    branch_id: str
    flow_config_version: str


@dataclass(frozen=True)
class LlmInvocationUsage:
    input_tokens: int
    output_tokens: int
    billing_quantity: int


@dataclass(frozen=True)
class LlmTextInvocationResult:
    content: str
    usage: LlmInvocationUsage


@dataclass(frozen=True)
class LlmToolInvocationResult:
    arguments: JsonObject
    usage: LlmInvocationUsage


@dataclass
class LlmUsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    billing_quantity: int = 0

    def add(self, usage: LlmInvocationUsage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.billing_quantity += usage.billing_quantity

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _json_string(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _llm_usage_tokens(metadata: JsonObject) -> tuple[int | None, int | None]:
    if "usage" not in metadata:
        return None, None
    usage = require_json_object(
        metadata["usage"],
        "evaluation_lab.llm_event.metadata.usage",
    )
    return (
        _llm_usage_token_count(usage, "input_tokens"),
        _llm_usage_token_count(usage, "output_tokens"),
    )


def _llm_usage_token_count(usage: JsonObject, field_name: str) -> int | None:
    if field_name not in usage:
        return None
    raw_tokens = usage[field_name]
    if not isinstance(raw_tokens, int) or isinstance(raw_tokens, bool):
        raise EvaluationLabValidationError(f"llm usage {field_name} must be an int")
    return raw_tokens


class EvaluationLabService:
    """Application service for suites, cases, immutable runs and UI events."""

    def __init__(
        self,
        *,
        repository: EvaluationLabRepository,
        flow_repository: FlowRepository,
        flow_factory: FlowFactory,
        node_registry: NodeRegistry,
        node_repository: NodeRepository,
        span_repository: SpanRepository,
    ):
        self._repository: EvaluationLabRepository = repository
        self._flow_repository: FlowRepository = flow_repository
        self._flow_factory: FlowFactory = flow_factory
        self._node_registry: NodeRegistry = node_registry
        self._node_repository: NodeRepository = node_repository
        self._span_repository: SpanRepository = span_repository
        self._event_locks: dict[str, asyncio.Lock] = {}

    async def create_suite(self, request: EvaluationSuiteCreateRequest) -> EvaluationSuite:
        flow = await self._flow_repository.get(request.flow_id)
        if flow is None:
            raise EvaluationLabNotFoundError(f"Flow not found: {request.flow_id}")
        now = _utc_now()
        suite = EvaluationSuite(
            suite_id=_new_id(),
            flow_id=request.flow_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_suite(suite)

    async def update_suite(
        self,
        suite_id: str,
        request: EvaluationSuiteUpdateRequest,
    ) -> EvaluationSuite:
        existing = await self._require_suite(suite_id)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "description": request.description,
                "tags": request.tags,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_suite(updated)

    async def archive_suite(self, suite_id: str) -> EvaluationSuite:
        existing = await self._require_suite(suite_id)
        if existing.archived_at is not None:
            return existing
        archived = existing.model_copy(
            update={"archived_at": _utc_now(), "updated_at": _utc_now()}
        )
        return await self._repository.update_suite(archived)

    async def get_suite(self, suite_id: str) -> EvaluationSuite:
        return await self._require_suite(suite_id)

    async def list_suites(self, flow_id: str) -> list[EvaluationSuite]:
        return await self._repository.list_suites(flow_id)

    def list_builtin_evaluators(self) -> EvaluationBuiltinEvaluatorCatalog:
        return EvaluationBuiltinEvaluatorCatalog(
            items=[
                EvaluationBuiltinEvaluator(
                    evaluator_id="contains",
                    name="Contains",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="Checks that response or state text contains required values.",
                    check_type="contains",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=10.0,
                    requires_reference=False,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id="not_contains",
                    name="Not contains",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="Checks that response or state text excludes blocked values.",
                    check_type="not_contains",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=10.0,
                    requires_reference=False,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id="regex",
                    name="Regex",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="Checks response or state text with a regular expression.",
                    check_type="regex",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=10.0,
                    requires_reference=False,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id="json_schema",
                    name="JSON schema",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="Validates response or state against a JSON Schema.",
                    check_type="json_schema",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=10.0,
                    requires_reference=False,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.ROUGE_L,
                    name="ROUGE-L",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="Longest-common-subsequence overlap against a reference answer.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.ROUGE_L
                    ],
                    requires_reference=True,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.BLEU,
                    name="BLEU",
                    category=EvaluationBuiltinEvaluatorCategory.DETERMINISTIC,
                    description="N-gram precision against a reference answer with brevity penalty.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.BLEU
                    ],
                    requires_reference=True,
                    requires_llm=False,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.TOXICITY,
                    name="Toxicity",
                    category=EvaluationBuiltinEvaluatorCategory.SAFETY,
                    description="LLM-judged non-toxicity score on a strict 0-10 scale.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.TOXICITY
                    ],
                    requires_reference=False,
                    requires_llm=True,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.SAFETY,
                    name="Safety",
                    category=EvaluationBuiltinEvaluatorCategory.SAFETY,
                    description="LLM-judged safety/compliance score on a strict 0-10 scale.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.SAFETY
                    ],
                    requires_reference=False,
                    requires_llm=True,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.GROUNDEDNESS,
                    name="Groundedness",
                    category=EvaluationBuiltinEvaluatorCategory.RETRIEVAL,
                    description="LLM-judged grounding against explicit reference/context.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.GROUNDEDNESS
                    ],
                    requires_reference=True,
                    requires_llm=True,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.ANSWER_RELEVANCE,
                    name="Answer relevance",
                    category=EvaluationBuiltinEvaluatorCategory.LLM_JUDGE,
                    description="LLM-judged relevance to the user task.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.ANSWER_RELEVANCE
                    ],
                    requires_reference=True,
                    requires_llm=True,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id=EvaluationBuiltinMetricId.TOOL_ACCURACY,
                    name="Tool accuracy",
                    category=EvaluationBuiltinEvaluatorCategory.TRACE,
                    description="LLM-judged correctness of tool use against expected behavior.",
                    check_type="builtin_metric",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=BUILTIN_METRIC_DEFAULT_THRESHOLDS[
                        EvaluationBuiltinMetricId.TOOL_ACCURACY
                    ],
                    requires_reference=True,
                    requires_llm=True,
                    supports_pairwise=False,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id="pairwise_llm",
                    name="Pairwise LLM judge",
                    category=EvaluationBuiltinEvaluatorCategory.PAIRWISE,
                    description="LLM chooses the better case run under a versioned rubric.",
                    check_type="pairwise_judgment",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=None,
                    requires_reference=False,
                    requires_llm=True,
                    supports_pairwise=True,
                ),
                EvaluationBuiltinEvaluator(
                    evaluator_id="pairwise_human",
                    name="Pairwise human judge",
                    category=EvaluationBuiltinEvaluatorCategory.PAIRWISE,
                    description="Human chooses the better case run with structured notes.",
                    check_type="pairwise_judgment",
                    score_min=0.0,
                    score_max=10.0,
                    default_threshold=None,
                    requires_reference=False,
                    requires_llm=False,
                    supports_pairwise=True,
                ),
            ]
        )

    async def create_case(
        self,
        suite_id: str,
        request: EvaluationCaseCreateRequest,
    ) -> EvaluationCase:
        suite = await self._require_suite(suite_id)
        now = _utc_now()
        case = EvaluationCase(
            case_id=_new_id(),
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            name=request.name,
            description=request.description,
            branch_ids=request.branch_ids,
            target=request.target,
            initial_state=request.initial_state,
            turns=request.turns,
            max_turns=request.max_turns,
            timeout_seconds=request.timeout_seconds,
            enabled=request.enabled,
            tags=request.tags,
            sort_order=request.sort_order,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_case(case)

    async def update_case(
        self,
        suite_id: str,
        case_id: str,
        request: EvaluationCaseUpdateRequest,
    ) -> EvaluationCase:
        existing = await self._require_case(suite_id, case_id)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "description": request.description,
                "branch_ids": request.branch_ids,
                "target": request.target,
                "initial_state": request.initial_state,
                "turns": request.turns,
                "max_turns": request.max_turns,
                "timeout_seconds": request.timeout_seconds,
                "enabled": request.enabled,
                "tags": request.tags,
                "sort_order": request.sort_order,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_case(updated)

    async def delete_case(self, suite_id: str, case_id: str) -> None:
        deleted = await self._repository.delete_case(suite_id, case_id)
        if not deleted:
            raise EvaluationLabNotFoundError(f"Evaluation case not found: {case_id}")

    async def get_case(self, suite_id: str, case_id: str) -> EvaluationCase:
        return await self._require_case(suite_id, case_id)

    async def list_cases(self, suite_id: str) -> list[EvaluationCase]:
        _ = await self._require_suite(suite_id)
        return await self._repository.list_cases(suite_id)

    async def import_cases(
        self,
        suite_id: str,
        request: EvaluationCaseImportRequest,
    ) -> EvaluationCaseImportResult:
        if request.format == EvaluationCaseImportFormat.JSONL:
            case_requests = self._parse_jsonl_case_import(request.content)
        elif request.format == EvaluationCaseImportFormat.CSV:
            case_requests = self._parse_csv_case_import(request.content)
        else:
            raise EvaluationLabValidationError(f"Unsupported case import format: {request.format}")
        cases: list[EvaluationCase] = []
        for case_request in case_requests:
            cases.append(await self.create_case(suite_id, case_request))
        return EvaluationCaseImportResult(cases=cases)

    async def create_case_from_dialog(
        self,
        suite_id: str,
        request: EvaluationDialogCaseCreateRequest,
    ) -> EvaluationCase:
        turns = self._dialog_to_turns(request.dialog, request.checks)
        return await self.create_case(
            suite_id,
            EvaluationCaseCreateRequest(
                name=request.name,
                description=request.description,
                branch_ids=request.branch_ids,
                turns=turns,
                tags=request.tags,
                sort_order=request.sort_order,
            ),
        )

    async def create_case_from_case_run(
        self,
        suite_id: str,
        request: EvaluationCaseRunCaseCreateRequest,
    ) -> EvaluationCase:
        run_id = await self._run_id_for_case_run(request.case_run_id)
        run_with_cases = await self.get_run(run_id)
        if run_with_cases.run.suite_id != suite_id:
            raise EvaluationLabValidationError(
                "Evaluation case run does not belong to requested suite"
            )
        case_run = self._case_run_by_id(run_with_cases.case_runs, request.case_run_id)
        turns = self._dialog_to_turns(case_run.dialog, request.checks)
        return await self.create_case(
            suite_id,
            EvaluationCaseCreateRequest(
                name=request.name,
                description=request.description,
                branch_ids=[run_with_cases.run.branch_id],
                turns=turns,
                tags=request.tags,
                sort_order=request.sort_order,
            ),
        )

    async def create_case_from_trace(
        self,
        suite_id: str,
        request: EvaluationTraceCaseCreateRequest,
    ) -> EvaluationCase:
        _ = await self._require_trace(request.trace_id)
        turns = self._dialog_to_turns(request.dialog, request.checks)
        return await self.create_case(
            suite_id,
            EvaluationCaseCreateRequest(
                name=request.name,
                description=request.description,
                branch_ids=request.branch_ids,
                turns=turns,
                tags=request.tags,
                sort_order=request.sort_order,
            ),
        )

    async def create_case_from_monitor_observation(
        self,
        monitor_id: str,
        trace_id: str,
        request: EvaluationMonitorObservationCaseCreateRequest,
    ) -> EvaluationMonitorObservationCurationResult:
        monitor = await self._require_monitor(monitor_id)
        observation = await self._require_monitor_observation(monitor_id, trace_id)
        if observation.suite_id != monitor.suite_id:
            raise EvaluationLabValidationError(
                "Monitor observation does not belong to monitor suite"
            )
        turns = self._dialog_to_turns(request.dialog, request.checks)
        case = await self.create_case(
            monitor.suite_id,
            EvaluationCaseCreateRequest(
                name=request.name,
                description=request.description,
                branch_ids=[monitor.branch_id],
                turns=turns,
                tags=request.tags,
                sort_order=request.sort_order,
            ),
        )
        curated_payload = dict(observation.payload)
        curated_payload["curated_case_id"] = case.case_id
        updated_observation = await self._repository.update_monitor_observation(
            observation.model_copy(
                update={
                    "state": EvaluationMonitorObservationState.CURATED,
                    "curated_case_id": case.case_id,
                    "payload": curated_payload,
                }
            )
        )
        return EvaluationMonitorObservationCurationResult(
            case=case,
            observation=updated_observation,
        )

    async def create_rubric(
        self,
        request: EvaluationRubricCreateRequest,
    ) -> tuple[EvaluationRubric, EvaluationRubricVersion]:
        flow = await self._flow_repository.get(request.flow_id)
        if flow is None:
            raise EvaluationLabNotFoundError(f"Flow not found: {request.flow_id}")
        now = _utc_now()
        rubric = EvaluationRubric(
            rubric_id=_new_id(),
            flow_id=request.flow_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            created_at=now,
            updated_at=now,
        )
        version = EvaluationRubricVersion(
            rubric_version_id=_new_id(),
            rubric_id=rubric.rubric_id,
            flow_id=rubric.flow_id,
            version=1,
            prompt=request.prompt,
            pass_threshold=request.pass_threshold,
            created_at=now,
        )
        return await self._repository.create_rubric(rubric, version)

    async def update_rubric(
        self,
        rubric_id: str,
        request: EvaluationRubricUpdateRequest,
    ) -> EvaluationRubric:
        rubric = await self._require_rubric(rubric_id)
        updated = rubric.model_copy(
            update={
                "name": request.name,
                "description": request.description,
                "tags": request.tags,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_rubric(updated)

    async def archive_rubric(self, rubric_id: str) -> EvaluationRubric:
        rubric = await self._require_rubric(rubric_id)
        if rubric.archived_at is not None:
            return rubric
        archived = rubric.model_copy(
            update={"archived_at": _utc_now(), "updated_at": _utc_now()}
        )
        return await self._repository.update_rubric(archived)

    async def get_rubric(self, rubric_id: str) -> EvaluationRubric:
        return await self._require_rubric(rubric_id)

    async def list_rubrics(self, flow_id: str) -> list[EvaluationRubric]:
        return await self._repository.list_rubrics(flow_id)

    async def create_rubric_version(
        self,
        rubric_id: str,
        request: EvaluationRubricVersionCreateRequest,
    ) -> EvaluationRubricVersion:
        rubric = await self._require_rubric(rubric_id)
        version_number = await self._repository.next_rubric_version(rubric_id)
        version = EvaluationRubricVersion(
            rubric_version_id=_new_id(),
            rubric_id=rubric.rubric_id,
            flow_id=rubric.flow_id,
            version=version_number,
            prompt=request.prompt,
            pass_threshold=request.pass_threshold,
            created_at=_utc_now(),
        )
        return await self._repository.create_rubric_version(version)

    async def list_rubric_versions(self, rubric_id: str) -> list[EvaluationRubricVersion]:
        _ = await self._require_rubric(rubric_id)
        return await self._repository.list_rubric_versions(rubric_id)

    async def create_run(self, request: EvaluationRunCreateRequest) -> EvaluationRunWithCases:
        suite = await self._require_suite(request.suite_id)
        if request.idempotency_key is not None:
            existing_run = await self._repository.get_run_by_idempotency_key(
                suite_id=suite.suite_id,
                branch_id=request.branch_id,
                idempotency_key=request.idempotency_key,
            )
            if existing_run is not None:
                return await self.get_run(existing_run.run_id)
        selected_cases = await self._select_cases(
            suite_id=suite.suite_id,
            branch_id=request.branch_id,
            scope=request.scope,
        )
        if not selected_cases:
            raise EvaluationLabValidationError("No enabled evaluation cases selected")

        flow = await self._flow_repository.get(suite.flow_id)
        if flow is None:
            raise EvaluationLabNotFoundError(f"Flow not found: {suite.flow_id}")
        flow_config_version = flow.version.strip()
        if not flow_config_version:
            raise EvaluationLabValidationError(
                f"Flow has no persisted config version: {suite.flow_id}"
            )
        if request.gate_policy_id is not None:
            gate_policy = await self._require_gate_policy(request.gate_policy_id)
            if gate_policy.suite_id != suite.suite_id or gate_policy.branch_id != request.branch_id:
                raise EvaluationLabValidationError(
                    "Gate policy must belong to the requested suite and branch"
                )

        version_number = await self._repository.next_suite_version(suite.suite_id)
        now = _utc_now()
        suite_version = EvaluationSuiteVersion(
            suite_version_id=_new_id(),
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            flow_config_version=flow_config_version,
            version=version_number,
            suite_snapshot=suite,
            cases_snapshot=selected_cases,
            created_at=now,
        )
        suite_version = await self._repository.create_suite_version(suite_version)

        run = EvaluationRun(
            run_id=_new_id(),
            suite_id=suite.suite_id,
            suite_version_id=suite_version.suite_version_id,
            flow_id=suite.flow_id,
            flow_config_version=flow_config_version,
            branch_id=request.branch_id,
            trigger=request.trigger,
            scope=request.scope,
            state=EvaluationRunState.QUEUED,
            idempotency_key=request.idempotency_key,
            gate_policy_id=request.gate_policy_id,
            total_cases=len(selected_cases),
            trials=request.trials,
            max_concurrency=request.max_concurrency,
            total_case_runs=len(selected_cases) * request.trials,
            created_at=now,
            updated_at=now,
        )
        run = await self._repository.create_run(run)
        _ = await self._append_event(
            run.run_id,
            None,
            EvaluationEventType.RUN_CREATED,
            {
                "suite_id": suite.suite_id,
                "total_cases": len(selected_cases),
                "trials": request.trials,
                "max_concurrency": request.max_concurrency,
                "total_case_runs": len(selected_cases) * request.trials,
                "gate_policy_id": request.gate_policy_id,
                "flow_config_version": flow_config_version,
            },
        )
        return EvaluationRunWithCases(run=run, case_runs=[])

    async def create_run_job(
        self,
        run_id: str,
        *,
        context_data: JsonObject,
        trace_context: JsonObject | None,
    ) -> EvaluationRunJob:
        run = await self._require_run_model(run_id)
        if run.state != EvaluationRunState.QUEUED:
            raise EvaluationLabValidationError(
                f"Evaluation run job can only be created for queued run: {run.state}"
            )
        now = _utc_now()
        taskiq_task_id = run.taskiq_task_id
        if taskiq_task_id is None:
            taskiq_task_id = f"evaluation-run:{uuid.uuid4().hex}"
            _ = await self.set_run_taskiq_task_id(run.run_id, taskiq_task_id)
        job = EvaluationRunJob(
            run_job_id=_new_id(),
            run_id=run.run_id,
            taskiq_task_id=taskiq_task_id,
            state=EvaluationRunJobState.PENDING,
            context_data=context_data,
            trace_context=trace_context,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_run_job(job)

    async def get_run_job(self, run_id: str) -> EvaluationRunJob:
        job = await self._repository.get_run_job_by_run_id(run_id)
        if job is None:
            raise EvaluationLabNotFoundError(f"Evaluation run job not found: {run_id}")
        return job

    async def list_pending_run_jobs(self, limit: int) -> list[EvaluationRunJob]:
        return await self._repository.list_pending_run_jobs(limit)

    async def mark_run_job_enqueued(self, run_id: str) -> EvaluationRunJob:
        job = await self.get_run_job(run_id)
        now = _utc_now()
        return await self._repository.update_run_job(
            job.model_copy(
                update={
                    "state": EvaluationRunJobState.ENQUEUED,
                    "error": None,
                    "enqueued_at": now,
                    "updated_at": now,
                }
            )
        )

    async def mark_run_job_failed(self, run_id: str, error: str) -> EvaluationRunJob:
        job = await self.get_run_job(run_id)
        return await self._repository.update_run_job(
            job.model_copy(
                update={
                    "state": EvaluationRunJobState.FAILED,
                    "error": error,
                    "updated_at": _utc_now(),
                }
            )
        )

    async def set_run_taskiq_task_id(
        self,
        run_id: str,
        taskiq_task_id: str,
    ) -> EvaluationRun:
        if not taskiq_task_id.strip():
            raise EvaluationLabValidationError("taskiq_task_id must be non-empty")
        run = await self._require_run_model(run_id)
        updated = run.model_copy(update={"taskiq_task_id": taskiq_task_id, "updated_at": _utc_now()})
        return await self._repository.update_run(updated)

    async def mark_run_enqueue_failed(self, run_id: str, error: str) -> EvaluationRunWithCases:
        run = await self._require_run_model(run_id)
        now = _utc_now()
        failed_run = await self._repository.update_run(
            run.model_copy(
                update={
                    "state": EvaluationRunState.ERROR,
                    "error_case_runs": run.total_case_runs,
                    "finished_at": now,
                    "updated_at": now,
                }
            )
        )
        _ = await self._append_event(
            run_id,
            None,
            EvaluationEventType.RUN_FAILED,
            {"state": str(EvaluationRunState.ERROR), "error": error},
        )
        return EvaluationRunWithCases(run=failed_run, case_runs=[])

    async def execute_run_from_taskiq(
        self,
        run_id: str,
        execution: EvaluationTaskiqExecutionContext,
    ) -> EvaluationRunWithCases:
        if execution.task_name != TASK_EXECUTE_EVALUATION_RUN:
            raise EvaluationLabValidationError(
                f"Evaluation run can only be executed by TaskIQ task {TASK_EXECUTE_EVALUATION_RUN}"
            )
        if execution.evaluation_run_id != run_id:
            raise EvaluationLabValidationError(
                "Evaluation run can only be executed by a TaskIQ message labeled for that run"
            )
        run = await self._require_run_model(run_id)
        if run.taskiq_task_id != execution.task_id:
            raise EvaluationLabValidationError(
                "Evaluation run can only be executed by its queued TaskIQ task"
            )
        job = await self.get_run_job(run_id)
        if job.taskiq_task_id != execution.task_id:
            raise EvaluationLabValidationError(
                "Evaluation run job must match the executing TaskIQ task"
            )
        if job.state != EvaluationRunJobState.ENQUEUED:
            raise EvaluationLabValidationError(
                f"Evaluation run job cannot execute from state: {job.state}"
            )
        if run.state == EvaluationRunState.CANCELED:
            return await self.get_run(run_id)
        if run.state != EvaluationRunState.QUEUED:
            raise EvaluationLabValidationError(
                f"Evaluation run cannot be executed from state: {run.state}"
            )
        suite_version = await self._require_suite_version(run.suite_version_id)
        run = run.model_copy(
            update={
                "state": EvaluationRunState.RUNNING,
                "started_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        run = await self._repository.update_run(run)
        _ = await self._append_event(
            run.run_id,
            None,
            EvaluationEventType.RUN_STARTED,
            {
                "branch_id": run.branch_id,
                "flow_config_version": run.flow_config_version,
                "suite_version_id": suite_version.suite_version_id,
            },
        )

        completed_case_runs: list[EvaluationCaseRun] = []
        semaphore = asyncio.Semaphore(run.max_concurrency)

        async def execute_case_trial(case: EvaluationCase, trial_index: int) -> EvaluationCaseRun:
            async with semaphore:
                return await self._run_case(run, case, trial_index)

        case_trial_tasks = [
            execute_case_trial(case, trial_index)
            for case in suite_version.cases_snapshot
            for trial_index in range(1, run.trials + 1)
        ]
        for completed in asyncio.as_completed(case_trial_tasks):
            completed_case_runs.append(await completed)

        latest_run = await self._require_run_model(run.run_id)
        canceled = latest_run.state == EvaluationRunState.CANCELED
        run = await self._finish_run(latest_run, completed_case_runs, force_canceled=canceled)
        if run.state == EvaluationRunState.CANCELED:
            return EvaluationRunWithCases(run=run, case_runs=completed_case_runs)
        gate_result = await self._evaluate_gate(run)
        if gate_result is not None:
            run = await self._require_run_model(run.run_id)
        event_type = (
            EvaluationEventType.RUN_FAILED
            if run.state == EvaluationRunState.ERROR
            else EvaluationEventType.RUN_FINISHED
        )
        _ = await self._append_event(
            run.run_id,
            None,
            event_type,
            {
                "state": str(run.state),
                "gate_state": str(run.gate_state) if run.gate_state is not None else None,
                "passed_case_runs": run.passed_case_runs,
                "failed_case_runs": run.failed_case_runs,
                "error_case_runs": run.error_case_runs,
                "canceled_case_runs": run.canceled_case_runs,
                "average_score": run.average_score,
                "average_duration_ms": run.average_duration_ms,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "total_tokens": run.total_tokens,
                "billing_quantity": run.billing_quantity,
            },
        )
        return EvaluationRunWithCases(run=run, case_runs=completed_case_runs, gate_result=gate_result)

    async def get_run(self, run_id: str) -> EvaluationRunWithCases:
        run = await self._repository.get_run_with_cases(run_id)
        if run is None:
            raise EvaluationLabNotFoundError(f"Evaluation run not found: {run_id}")
        return run

    async def list_runs(self, suite_id: str, limit: int) -> list[EvaluationRun]:
        _ = await self._require_suite(suite_id)
        return await self._repository.list_runs(suite_id, limit)

    async def list_events(self, run_id: str) -> list[EvaluationRunEvent]:
        _ = await self.get_run(run_id)
        return await self._repository.list_events(run_id)

    async def list_events_page(
        self,
        run_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> EvaluationRunEventsPage:
        _ = await self.get_run(run_id)
        rows = await self._repository.list_events_after_sequence(
            run_id,
            after_sequence=after_sequence,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_sequence = items[-1].sequence if has_more and items else None
        return EvaluationRunEventsPage(
            items=items,
            next_sequence=next_sequence,
            has_more=has_more,
        )

    async def list_case_runs(self, run_id: str) -> list[EvaluationCaseRun]:
        _ = await self.get_run(run_id)
        return await self._repository.list_case_runs(run_id)

    async def cancel_run(self, run_id: str) -> EvaluationRunWithCases:
        run_with_cases = await self.get_run(run_id)
        run = run_with_cases.run
        if run.state not in {EvaluationRunState.QUEUED, EvaluationRunState.RUNNING}:
            raise EvaluationLabValidationError(
                f"Evaluation run cannot be canceled from state: {run.state}"
            )
        passed = sum(
            1
            for case_run in run_with_cases.case_runs
            if case_run.state == EvaluationCaseRunState.PASSED
        )
        failed = sum(
            1
            for case_run in run_with_cases.case_runs
            if case_run.state == EvaluationCaseRunState.FAILED
        )
        errors = sum(
            1
            for case_run in run_with_cases.case_runs
            if case_run.state == EvaluationCaseRunState.ERROR
        )
        input_tokens = sum(case_run.input_tokens for case_run in run_with_cases.case_runs)
        output_tokens = sum(case_run.output_tokens for case_run in run_with_cases.case_runs)
        total_tokens = sum(case_run.total_tokens for case_run in run_with_cases.case_runs)
        billing_quantity = sum(case_run.billing_quantity for case_run in run_with_cases.case_runs)
        canceled = max(run.total_case_runs - passed - failed - errors, 0)
        now = _utc_now()
        canceled_run = await self._repository.update_run(
            run.model_copy(
                update={
                    "state": EvaluationRunState.CANCELED,
                    "passed_case_runs": passed,
                    "failed_case_runs": failed,
                    "error_case_runs": errors,
                    "canceled_case_runs": canceled,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "billing_quantity": billing_quantity,
                    "finished_at": now,
                    "updated_at": now,
                }
            )
        )
        _ = await self._append_event(
            run_id,
            None,
            EvaluationEventType.RUN_CANCELED,
            {
                "state": str(EvaluationRunState.CANCELED),
                "passed_case_runs": passed,
                "failed_case_runs": failed,
                "error_case_runs": errors,
                "canceled_case_runs": canceled,
            },
        )
        return EvaluationRunWithCases(run=canceled_run, case_runs=run_with_cases.case_runs)

    async def create_annotation(
        self,
        run_id: str,
        request: EvaluationAnnotationCreateRequest,
    ) -> EvaluationAnnotation:
        run_with_cases = await self.get_run(run_id)
        case_id = request.case_id
        if request.case_run_id is not None:
            case_run = self._case_run_by_id(run_with_cases.case_runs, request.case_run_id)
            case_id = case_run.case_id
        now = _utc_now()
        annotation = EvaluationAnnotation(
            annotation_id=_new_id(),
            run_id=run_id,
            case_run_id=request.case_run_id,
            case_id=case_id,
            annotation_type=request.annotation_type,
            comment=request.comment,
            payload=request.payload,
            created_by=self._current_user_id(),
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_annotation(annotation)

    async def list_annotations(self, run_id: str) -> list[EvaluationAnnotation]:
        _ = await self.get_run(run_id)
        return await self._repository.list_annotations(run_id)

    async def update_annotation(
        self,
        annotation_id: str,
        request: EvaluationAnnotationUpdateRequest,
    ) -> EvaluationAnnotation:
        annotation = await self._require_annotation(annotation_id)
        updated = annotation.model_copy(
            update={
                "annotation_type": request.annotation_type,
                "comment": request.comment,
                "payload": request.payload,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_annotation(updated)

    async def delete_annotation(self, annotation_id: str) -> None:
        deleted = await self._repository.delete_annotation(annotation_id)
        if not deleted:
            raise EvaluationLabNotFoundError(f"Evaluation annotation not found: {annotation_id}")

    async def set_baseline(
        self,
        suite_id: str,
        branch_id: str,
        request: EvaluationBaselineSetRequest,
    ) -> EvaluationBaseline:
        suite = await self._require_suite(suite_id)
        run = await self._require_run_model(request.run_id)
        if run.suite_id != suite_id or run.branch_id != branch_id:
            raise EvaluationLabValidationError(
                "Baseline run must belong to the requested suite and branch"
            )
        if run.state in {EvaluationRunState.QUEUED, EvaluationRunState.RUNNING}:
            raise EvaluationLabValidationError("Baseline run must be terminal")
        now = _utc_now()
        baseline = EvaluationBaseline(
            baseline_id=_new_id(),
            suite_id=suite_id,
            flow_id=suite.flow_id,
            branch_id=branch_id,
            run_id=run.run_id,
            created_by=self._current_user_id(),
            created_at=now,
            updated_at=now,
        )
        return await self._repository.upsert_baseline(baseline)

    async def get_baseline(self, suite_id: str, branch_id: str) -> EvaluationBaseline:
        _ = await self._require_suite(suite_id)
        baseline = await self._repository.get_baseline(suite_id, branch_id)
        if baseline is None:
            raise EvaluationLabNotFoundError(f"Evaluation baseline not found: {branch_id}")
        return baseline

    async def list_baselines(self, suite_id: str) -> list[EvaluationBaseline]:
        _ = await self._require_suite(suite_id)
        return await self._repository.list_baselines(suite_id)

    async def create_gate_policy(
        self,
        suite_id: str,
        request: EvaluationGatePolicyCreateRequest,
    ) -> EvaluationGatePolicy:
        suite = await self._require_suite(suite_id)
        now = _utc_now()
        policy = EvaluationGatePolicy(
            gate_policy_id=_new_id(),
            suite_id=suite_id,
            flow_id=suite.flow_id,
            branch_id=request.branch_id,
            name=request.name,
            min_pass_rate=request.min_pass_rate,
            min_average_score=request.min_average_score,
            max_failed_case_runs=request.max_failed_case_runs,
            max_error_case_runs=request.max_error_case_runs,
            max_average_duration_ms=request.max_average_duration_ms,
            require_baseline=request.require_baseline,
            min_baseline_score_delta=request.min_baseline_score_delta,
            max_baseline_duration_delta_ms=request.max_baseline_duration_delta_ms,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_gate_policy(policy)

    async def update_gate_policy(
        self,
        gate_policy_id: str,
        request: EvaluationGatePolicyUpdateRequest,
    ) -> EvaluationGatePolicy:
        policy = await self._require_gate_policy(gate_policy_id)
        updated = policy.model_copy(
            update={
                "branch_id": request.branch_id,
                "name": request.name,
                "min_pass_rate": request.min_pass_rate,
                "min_average_score": request.min_average_score,
                "max_failed_case_runs": request.max_failed_case_runs,
                "max_error_case_runs": request.max_error_case_runs,
                "max_average_duration_ms": request.max_average_duration_ms,
                "require_baseline": request.require_baseline,
                "min_baseline_score_delta": request.min_baseline_score_delta,
                "max_baseline_duration_delta_ms": request.max_baseline_duration_delta_ms,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_gate_policy(updated)

    async def archive_gate_policy(self, gate_policy_id: str) -> EvaluationGatePolicy:
        policy = await self._require_gate_policy(gate_policy_id)
        if policy.archived_at is not None:
            return policy
        archived = policy.model_copy(
            update={"archived_at": _utc_now(), "updated_at": _utc_now()}
        )
        return await self._repository.update_gate_policy(archived)

    async def get_gate_policy(self, gate_policy_id: str) -> EvaluationGatePolicy:
        return await self._require_gate_policy(gate_policy_id)

    async def list_gate_policies(self, suite_id: str) -> list[EvaluationGatePolicy]:
        _ = await self._require_suite(suite_id)
        return await self._repository.list_gate_policies(suite_id)

    async def create_gate_policy_run(
        self,
        gate_policy_id: str,
        request: EvaluationGatePolicyRunRequest,
    ) -> EvaluationRunWithCases:
        if request.trigger not in {EvaluationRunTrigger.CI, EvaluationRunTrigger.NIGHTLY}:
            raise EvaluationLabValidationError(
                "Gate policy run trigger must be ci or nightly"
            )
        policy = await self._require_gate_policy(gate_policy_id)
        return await self.create_run(
            EvaluationRunCreateRequest(
                suite_id=policy.suite_id,
                branch_id=policy.branch_id,
                trigger=request.trigger,
                scope=EvaluationRunSuiteScope(type="suite"),
                trials=request.trials,
                max_concurrency=request.max_concurrency,
                gate_policy_id=policy.gate_policy_id,
                idempotency_key=request.idempotency_key,
            )
        )

    async def get_gate_result(self, run_id: str) -> EvaluationGateResult:
        _ = await self._require_run_model(run_id)
        gate_result = await self._repository.get_gate_result(run_id)
        if gate_result is None:
            raise EvaluationLabNotFoundError(f"Evaluation gate result not found: {run_id}")
        return gate_result

    async def compare_runs(self, left_run_id: str, right_run_id: str) -> EvaluationRunComparison:
        left = await self.get_run(left_run_id)
        right = await self.get_run(right_run_id)
        left_cases = {
            (case_run.case_id, case_run.trial_index): case_run for case_run in left.case_runs
        }
        right_cases = {
            (case_run.case_id, case_run.trial_index): case_run for case_run in right.case_runs
        }
        case_keys = sorted(set(left_cases.keys()).union(right_cases.keys()))
        deltas: list[EvaluationCompareCaseDelta] = []
        for case_id, trial_index in case_keys:
            key = (case_id, trial_index)
            left_case = left_cases[key] if key in left_cases else None
            right_case = right_cases[key] if key in right_cases else None
            deltas.append(
                EvaluationCompareCaseDelta(
                    case_id=case_id,
                    trial_index=trial_index,
                    left=left_case,
                    right=right_case,
                    score_delta=self._score_delta(left_case, right_case),
                    duration_delta_ms=self._duration_delta(left_case, right_case),
                )
            )
        return EvaluationRunComparison(left_run=left.run, right_run=right.run, cases=deltas)

    async def compare_with_baseline(
        self,
        suite_id: str,
        branch_id: str,
        run_id: str,
    ) -> EvaluationBaselineComparison:
        baseline = await self.get_baseline(suite_id, branch_id)
        comparison = await self.compare_runs(baseline.run_id, run_id)
        return EvaluationBaselineComparison(baseline=baseline, comparison=comparison)

    async def get_results_matrix(
        self,
        suite_id: str,
        branch_id: str,
        limit: int,
    ) -> EvaluationResultsMatrix:
        _ = await self._require_suite(suite_id)
        all_cases = await self._repository.list_cases(suite_id)
        cases = [
            EvaluationMatrixCase(
                case_id=case.case_id,
                name=case.name,
                enabled=case.enabled,
                tags=case.tags,
                sort_order=case.sort_order,
            )
            for case in all_cases
            if self._case_matches_branch(case, branch_id)
        ]
        runs = [
            run
            for run in await self._repository.list_runs(suite_id, limit)
            if run.branch_id == branch_id
        ]
        matrix_runs = [
            EvaluationMatrixRun(
                run_id=run.run_id,
                state=run.state,
                gate_state=run.gate_state,
                total_case_runs=run.total_case_runs,
                passed_case_runs=run.passed_case_runs,
                failed_case_runs=run.failed_case_runs,
                error_case_runs=run.error_case_runs,
                canceled_case_runs=run.canceled_case_runs,
                average_score=run.average_score,
                average_duration_ms=run.average_duration_ms,
                billing_quantity=run.billing_quantity,
                created_at=run.created_at,
                finished_at=run.finished_at,
            )
            for run in runs
        ]
        cells: list[EvaluationMatrixCell] = []
        for run in runs:
            for case_run in await self._repository.list_case_runs(run.run_id):
                cells.append(
                    EvaluationMatrixCell(
                        run_id=run.run_id,
                        case_id=case_run.case_id,
                        trial_index=case_run.trial_index,
                        state=case_run.state,
                        total_score=case_run.total_score,
                        duration_ms=case_run.duration_ms,
                        billing_quantity=case_run.billing_quantity,
                        case_run_id=case_run.case_run_id,
                    )
                )
        return EvaluationResultsMatrix(
            suite_id=suite_id,
            branch_id=branch_id,
            cases=cases,
            runs=matrix_runs,
            cells=cells,
        )

    async def get_case_run_trace(self, case_run_id: str) -> EvaluationCaseRunTrace:
        run_id = await self._run_id_for_case_run(case_run_id)
        run_with_cases = await self.get_run(run_id)
        case_run = self._case_run_by_id(run_with_cases.case_runs, case_run_id)
        if case_run.session_id is None:
            raise EvaluationLabValidationError("Evaluation case run has no session_id")
        spans = []
        if case_run.trace_id is not None:
            spans = [
                self._trace_span(span)
                for span in await self._span_repository.get_trace(case_run.trace_id)
            ]
        workflow_records, _ = await self._flow_factory.container.workflow_runtime.get_state_history(
            case_run.session_id,
            limit=1000,
        )
        workflow_events = [self._workflow_event(record) for record in workflow_records]
        node_steps = self._trace_node_steps(workflow_records)
        return EvaluationCaseRunTrace(
            case_run=case_run,
            spans=spans,
            workflow_events=workflow_events,
            node_steps=node_steps,
            tool_calls=self._trace_tool_calls(workflow_records),
            state_diffs=self._trace_state_diffs(workflow_records),
        )

    async def create_monitor(
        self,
        request: EvaluationMonitorCreateRequest,
    ) -> EvaluationMonitor:
        suite = await self._require_suite(request.suite_id)
        if request.gate_policy_id is not None:
            policy = await self._require_gate_policy(request.gate_policy_id)
            if policy.suite_id != suite.suite_id or policy.branch_id != request.branch_id:
                raise EvaluationLabValidationError(
                    "Monitor gate policy must belong to the requested suite and branch"
                )
        now = _utc_now()
        monitor = EvaluationMonitor(
            monitor_id=_new_id(),
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            branch_id=request.branch_id,
            name=request.name,
            description=request.description,
            state=EvaluationMonitorState.ACTIVE,
            sampling_rate=request.sampling_rate,
            max_traces_per_sample=request.max_traces_per_sample,
            filter=request.filter,
            gate_policy_id=request.gate_policy_id,
            created_by=self._current_user_id(),
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_monitor(monitor)

    async def update_monitor(
        self,
        monitor_id: str,
        request: EvaluationMonitorUpdateRequest,
    ) -> EvaluationMonitor:
        existing = await self._require_monitor(monitor_id)
        if request.gate_policy_id is not None:
            policy = await self._require_gate_policy(request.gate_policy_id)
            if policy.suite_id != existing.suite_id or policy.branch_id != request.branch_id:
                raise EvaluationLabValidationError(
                    "Monitor gate policy must belong to the requested suite and branch"
                )
        updated = existing.model_copy(
            update={
                "branch_id": request.branch_id,
                "name": request.name,
                "description": request.description,
                "state": request.state,
                "sampling_rate": request.sampling_rate,
                "max_traces_per_sample": request.max_traces_per_sample,
                "filter": request.filter,
                "gate_policy_id": request.gate_policy_id,
                "updated_at": _utc_now(),
            }
        )
        return await self._repository.update_monitor(updated)

    async def archive_monitor(self, monitor_id: str) -> EvaluationMonitor:
        monitor = await self._require_monitor(monitor_id)
        if monitor.state == EvaluationMonitorState.ARCHIVED:
            return monitor
        archived = monitor.model_copy(
            update={"state": EvaluationMonitorState.ARCHIVED, "updated_at": _utc_now()}
        )
        return await self._repository.update_monitor(archived)

    async def list_monitors(self, suite_id: str) -> list[EvaluationMonitor]:
        _ = await self._require_suite(suite_id)
        return await self._repository.list_monitors(suite_id)

    async def get_monitor(self, monitor_id: str) -> EvaluationMonitor:
        return await self._require_monitor(monitor_id)

    async def sample_monitor(
        self,
        monitor_id: str,
        request: EvaluationMonitorSampleRequest,
    ) -> EvaluationMonitorSampleResult:
        monitor = await self._require_monitor(monitor_id)
        if monitor.state != EvaluationMonitorState.ACTIVE:
            raise EvaluationLabValidationError(
                f"Evaluation monitor cannot sample from state: {monitor.state}"
            )
        limit = min(request.limit, monitor.max_traces_per_sample)
        traces, _ = await self._span_repository.search_traces(
            user_id=monitor.filter.user_id,
            session_id=monitor.filter.session_id,
            flow_id=monitor.flow_id,
            from_time=monitor.filter.from_time,
            to_time=monitor.filter.to_time,
            limit=limit,
            offset=0,
        )
        observations: list[EvaluationMonitorObservation] = []
        for trace in traces:
            if not self._monitor_trace_is_sampled(trace.trace_id, monitor.sampling_rate):
                continue
            observation = self._monitor_observation(monitor, trace)
            observations.append(await self._repository.upsert_monitor_observation(observation))
        return EvaluationMonitorSampleResult(monitor=monitor, observations=observations)

    async def run_monitor_cycle(
        self,
        monitor_id: str,
        request: EvaluationMonitorCycleRequest,
    ) -> EvaluationMonitorCycleResult:
        sample = await self.sample_monitor(
            monitor_id,
            EvaluationMonitorSampleRequest(limit=request.limit),
        )
        created_run: EvaluationRun | None = None
        if sample.monitor.gate_policy_id is not None and request.enqueue_gate_run:
            run_with_cases = await self.create_gate_policy_run(
                sample.monitor.gate_policy_id,
                EvaluationGatePolicyRunRequest(
                    trigger=EvaluationRunTrigger.NIGHTLY,
                    trials=request.trials,
                    max_concurrency=request.max_concurrency,
                    idempotency_key=request.idempotency_key,
                ),
            )
            created_run = run_with_cases.run
        return EvaluationMonitorCycleResult(
            monitor=sample.monitor,
            observations=sample.observations,
            run=created_run,
        )

    async def run_active_monitor_cycles(
        self,
        *,
        limit_per_monitor: int,
        enqueue_gate_runs: bool,
        trials: int,
        max_concurrency: int,
    ) -> list[EvaluationMonitorCycleResult]:
        monitors = await self._repository.list_active_monitors(500)
        cycles: list[EvaluationMonitorCycleResult] = []
        for monitor in monitors:
            cycles.append(
                await self.run_monitor_cycle(
                    monitor.monitor_id,
                    EvaluationMonitorCycleRequest(
                        limit=limit_per_monitor,
                        enqueue_gate_run=enqueue_gate_runs,
                        trials=trials,
                        max_concurrency=max_concurrency,
                    ),
                )
            )
        return cycles

    async def list_monitor_observations(
        self,
        monitor_id: str,
        limit: int,
    ) -> list[EvaluationMonitorObservation]:
        _ = await self._require_monitor(monitor_id)
        return await self._repository.list_monitor_observations(monitor_id, limit)

    async def create_pairwise_judgment(
        self,
        request: EvaluationPairwiseJudgeRequest,
    ) -> EvaluationPairwiseJudgment:
        left = await self._require_case_run(request.left_case_run_id)
        right = await self._require_case_run(request.right_case_run_id)
        self._validate_pairwise_case_runs(left, right)
        if request.mode == EvaluationPairwiseJudgeMode.HUMAN:
            if request.preferred is None:
                raise EvaluationLabValidationError(
                    "Human pairwise judgment requires preferred"
                )
            if request.rubric_version_id is not None:
                _ = await self._require_rubric_version(request.rubric_version_id)
            preferred = request.preferred
            scores = request.scores
            feedback = request.feedback
        elif request.mode == EvaluationPairwiseJudgeMode.LLM:
            if request.rubric_version_id is None:
                raise EvaluationLabValidationError(
                    "LLM pairwise judgment requires rubric_version_id"
                )
            rubric_version = await self._require_rubric_version(request.rubric_version_id)
            llm_result = await self._judge_pairwise_with_llm(
                request=request,
                left=left,
                right=right,
                rubric_version=rubric_version,
            )
            preferred = llm_result.preferred
            scores = llm_result.scores
            feedback = llm_result.feedback
        else:
            raise EvaluationLabValidationError(f"Unsupported pairwise mode: {request.mode}")
        now = _utc_now()
        judgment = EvaluationPairwiseJudgment(
            pairwise_judgment_id=_new_id(),
            suite_id=left.suite_id,
            flow_id=left.flow_id,
            branch_id=left.branch_id,
            left_run_id=left.run_id,
            right_run_id=right.run_id,
            left_case_run_id=left.case_run_id,
            right_case_run_id=right.case_run_id,
            mode=request.mode,
            preferred=preferred,
            rubric_version_id=request.rubric_version_id,
            scores=scores,
            feedback=feedback,
            created_by=self._current_user_id(),
            created_at=now,
        )
        return await self._repository.create_pairwise_judgment(judgment)

    async def list_pairwise_judgments_for_case_run(
        self,
        case_run_id: str,
    ) -> list[EvaluationPairwiseJudgment]:
        _ = await self._require_case_run(case_run_id)
        return await self._repository.list_pairwise_judgments_for_case_run(case_run_id)

    async def _run_case(
        self,
        run: EvaluationRun,
        case: EvaluationCase,
        trial_index: int,
    ) -> EvaluationCaseRun:
        now = _utc_now()
        case_run = EvaluationCaseRun(
            case_run_id=_new_id(),
            run_id=run.run_id,
            case_id=case.case_id,
            trial_index=trial_index,
            suite_id=case.suite_id,
            flow_id=case.flow_id,
            branch_id=run.branch_id,
            state=EvaluationCaseRunState.QUEUED,
            trace_id=self._current_trace_id(),
            created_at=now,
            updated_at=now,
        )
        case_run = await self._repository.create_case_run(case_run)
        _ = await self._append_event(
            run.run_id,
            case_run.case_run_id,
            EvaluationEventType.CASE_STARTED,
            {"case_id": case.case_id, "name": case.name, "trial_index": trial_index},
        )

        started_at = _utc_now()
        task_id = _new_id()
        context_id = _new_id()
        case_run = case_run.model_copy(
            update={
                "state": EvaluationCaseRunState.RUNNING,
                "task_id": task_id,
                "context_id": context_id,
                "started_at": started_at,
                "updated_at": started_at,
            }
        )
        case_run = await self._repository.update_case_run(case_run)

        elapsed = self._elapsed_ms()
        dialog: list[EvaluationDialogMessage] = []
        scores: EvaluationScores = {}
        judge_feedback: str | None = None
        usage = LlmUsageAccumulator()
        turns_count = 0

        try:
            if await self._run_is_canceled(run.run_id):
                return await self._cancel_case_run(
                    run=run,
                    case=case,
                    case_run=case_run,
                    started_at=started_at,
                    duration_ms=elapsed(),
                    turns_count=turns_count,
                    dialog=dialog,
                    scores=None,
                    judge_feedback=None,
                    usage=usage,
                )
            target_runtime = await self._create_target_runtime(
                case,
                run.branch_id,
                run.flow_config_version,
            )
            session_id = f"{target_runtime.flow_id}:{context_id}"
            case_run = await self._repository.update_case_run(
                case_run.model_copy(
                    update={
                        "session_id": session_id,
                        "updated_at": _utc_now(),
                    }
                )
            )
            state = self._create_execution_state(
                case=case,
                target_runtime=target_runtime,
                task_id=task_id,
                context_id=context_id,
                session_id=session_id,
            )
            async with asyncio.timeout(case.timeout_seconds):
                for turn_index, turn in enumerate(case.turns):
                    if await self._run_is_canceled(run.run_id):
                        return await self._cancel_case_run(
                            run=run,
                            case=case,
                            case_run=case_run,
                            started_at=started_at,
                            duration_ms=elapsed(),
                            turns_count=turns_count,
                            dialog=dialog,
                            scores=scores if scores else None,
                            judge_feedback=judge_feedback,
                            usage=usage,
                        )
                    if turns_count >= case.max_turns:
                        raise EvaluationLabValidationError(
                            f"Case {case.case_id} exceeded max_turns={case.max_turns}"
                        )
                    turns_count += 1
                    _ = await self._append_event(
                        run.run_id,
                        case_run.case_run_id,
                        EvaluationEventType.TURN_STARTED,
                        {"turn_index": turn_index, "trial_index": trial_index},
                    )
                    input_text = await self._input_to_text(turn.input, state, dialog, usage)
                    dialog.append(EvaluationDialogMessage(role="user", content=input_text))
                    _ = await self._append_event(
                        run.run_id,
                        case_run.case_run_id,
                        EvaluationEventType.MESSAGE_RECORDED,
                        {
                            "role": "user",
                            "content": input_text,
                            "turn_index": turn_index,
                            "trial_index": trial_index,
                        },
                    )

                    state.content = input_text
                    state.branch_id = target_runtime.branch_id
                    state = await target_runtime.callable(state)
                    response = state.response if state.response is not None else ""
                    dialog.append(EvaluationDialogMessage(role="assistant", content=response))
                    _ = await self._append_event(
                        run.run_id,
                        case_run.case_run_id,
                        EvaluationEventType.MESSAGE_RECORDED,
                        {
                            "role": "assistant",
                            "content": response,
                            "turn_index": turn_index,
                            "trial_index": trial_index,
                        },
                    )

                    state_json = require_json_object(
                        state.model_dump(mode="json", exclude_none=False),
                        "evaluation.execution_state",
                    )
                    if await self._run_is_canceled(run.run_id):
                        return await self._cancel_case_run(
                            run=run,
                            case=case,
                            case_run=case_run,
                            started_at=started_at,
                            duration_ms=elapsed(),
                            turns_count=turns_count,
                            dialog=dialog,
                            scores=scores if scores else None,
                            judge_feedback=judge_feedback,
                            usage=usage,
                        )
                    for check_index, check in enumerate(turn.checks):
                        if await self._run_is_canceled(run.run_id):
                            return await self._cancel_case_run(
                                run=run,
                                case=case,
                                case_run=case_run,
                                started_at=started_at,
                                duration_ms=elapsed(),
                                turns_count=turns_count,
                                dialog=dialog,
                                scores=scores if scores else None,
                                judge_feedback=judge_feedback,
                                usage=usage,
                            )
                        _ = await self._append_event(
                            run.run_id,
                            case_run.case_run_id,
                            EvaluationEventType.CHECK_STARTED,
                            {
                                "turn_index": turn_index,
                                "check_index": check_index,
                                "check_type": check.type,
                                "trial_index": trial_index,
                            },
                        )
                        outcome = await self._evaluate_check(
                            check=check,
                            state=state,
                            state_json=state_json,
                            response=response,
                            dialog=dialog,
                            usage=usage,
                        )
                        for key, score in outcome.scores.items():
                            scores[f"turn_{turn_index + 1}.check_{check_index + 1}.{key}"] = score
                        if outcome.feedback is not None:
                            judge_feedback = outcome.feedback
                        _ = await self._append_event(
                            run.run_id,
                            case_run.case_run_id,
                            EvaluationEventType.SCORE_RECORDED,
                            {
                                "turn_index": turn_index,
                                "check_index": check_index,
                                "scores": self._scores_to_json(outcome.scores),
                                "passed": outcome.passed,
                                "trial_index": trial_index,
                            },
                        )
                        if not outcome.passed:
                            case_run = await self._finish_case_run(
                                case_run=case_run,
                                state=EvaluationCaseRunState.FAILED,
                                started_at=started_at,
                                duration_ms=elapsed(),
                                turns_count=turns_count,
                                dialog=dialog,
                                scores=scores,
                                judge_feedback=judge_feedback,
                                usage=usage,
                                error=f"Turn {turn_index + 1} check {check_index + 1} failed",
                            )
                            _ = await self._append_event(
                                run.run_id,
                                case_run.case_run_id,
                                EvaluationEventType.CASE_FINISHED,
                                {
                                    "state": str(case_run.state),
                                    "case_id": case.case_id,
                                    "trial_index": trial_index,
                                },
                            )
                            return case_run

            if not scores:
                scores = {"result": 10.0}
            case_run = await self._finish_case_run(
                case_run=case_run,
                state=EvaluationCaseRunState.PASSED,
                started_at=started_at,
                duration_ms=elapsed(),
                turns_count=turns_count,
                dialog=dialog,
                scores=scores,
                judge_feedback=judge_feedback,
                usage=usage,
                error=None,
            )
            _ = await self._append_event(
                run.run_id,
                case_run.case_run_id,
                EvaluationEventType.CASE_FINISHED,
                {
                    "state": str(case_run.state),
                    "case_id": case.case_id,
                    "trial_index": trial_index,
                },
            )
            return case_run
        except Exception as exc:
            logger.exception("Evaluation case failed: case_id=%s", case.case_id)
            case_run = await self._finish_case_run(
                case_run=case_run,
                state=EvaluationCaseRunState.ERROR,
                started_at=started_at,
                duration_ms=elapsed(),
                turns_count=turns_count,
                dialog=dialog,
                scores=scores if scores else None,
                judge_feedback=judge_feedback,
                usage=usage,
                error=str(exc),
            )
            _ = await self._append_event(
                run.run_id,
                case_run.case_run_id,
                EvaluationEventType.CASE_FAILED,
                {"case_id": case.case_id, "trial_index": trial_index, "error": str(exc)},
            )
            return case_run

    async def _cancel_case_run(
        self,
        *,
        run: EvaluationRun,
        case: EvaluationCase,
        case_run: EvaluationCaseRun,
        started_at: datetime,
        duration_ms: int,
        turns_count: int,
        dialog: list[EvaluationDialogMessage],
        scores: EvaluationScores | None,
        judge_feedback: str | None,
        usage: LlmUsageAccumulator,
    ) -> EvaluationCaseRun:
        canceled_case_run = await self._finish_case_run(
            case_run=case_run,
            state=EvaluationCaseRunState.CANCELED,
            started_at=started_at,
            duration_ms=duration_ms,
            turns_count=turns_count,
            dialog=dialog,
            scores=scores,
            judge_feedback=judge_feedback,
            usage=usage,
            error="Evaluation run canceled",
        )
        _ = await self._append_event(
            run.run_id,
            canceled_case_run.case_run_id,
            EvaluationEventType.CASE_CANCELED,
            {"case_id": case.case_id, "trial_index": canceled_case_run.trial_index},
        )
        _ = await self._append_event(
            run.run_id,
            canceled_case_run.case_run_id,
            EvaluationEventType.CASE_FINISHED,
            {
                "state": str(canceled_case_run.state),
                "case_id": case.case_id,
                "trial_index": canceled_case_run.trial_index,
            },
        )
        return canceled_case_run

    async def _finish_case_run(
        self,
        *,
        case_run: EvaluationCaseRun,
        state: EvaluationCaseRunState,
        started_at: datetime,
        duration_ms: int,
        turns_count: int,
        dialog: list[EvaluationDialogMessage],
        scores: EvaluationScores | None,
        judge_feedback: str | None,
        usage: LlmUsageAccumulator,
        error: str | None,
    ) -> EvaluationCaseRun:
        finished_at = _utc_now()
        return await self._repository.update_case_run(
            case_run.model_copy(
                update={
                    "state": state,
                    "duration_ms": duration_ms,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "billing_quantity": usage.billing_quantity,
                    "turns_count": turns_count,
                    "scores": scores,
                    "total_score": self._total_score(scores),
                    "judge_feedback": judge_feedback,
                    "dialog": dialog,
                    "error": error,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        )

    async def _finish_run(
        self,
        run: EvaluationRun,
        case_runs: list[EvaluationCaseRun],
        *,
        force_canceled: bool = False,
    ) -> EvaluationRun:
        passed = sum(1 for case_run in case_runs if case_run.state == EvaluationCaseRunState.PASSED)
        failed = sum(1 for case_run in case_runs if case_run.state == EvaluationCaseRunState.FAILED)
        errors = sum(1 for case_run in case_runs if case_run.state == EvaluationCaseRunState.ERROR)
        canceled = sum(1 for case_run in case_runs if case_run.state == EvaluationCaseRunState.CANCELED)
        if force_canceled:
            canceled = max(run.total_case_runs - passed - failed - errors, canceled)
        total_scores = [
            case_run.total_score
            for case_run in case_runs
            if case_run.total_score is not None
        ]
        average_score = sum(total_scores) / len(total_scores) if total_scores else None
        durations = [
            case_run.duration_ms
            for case_run in case_runs
            if case_run.duration_ms is not None
        ]
        average_duration_ms = sum(durations) / len(durations) if durations else None
        input_tokens = sum(case_run.input_tokens for case_run in case_runs)
        output_tokens = sum(case_run.output_tokens for case_run in case_runs)
        total_tokens = sum(case_run.total_tokens for case_run in case_runs)
        billing_quantity = sum(case_run.billing_quantity for case_run in case_runs)
        if force_canceled:
            state = EvaluationRunState.CANCELED
        elif errors > 0:
            state = EvaluationRunState.ERROR
        elif failed > 0:
            state = EvaluationRunState.FAILED
        else:
            state = EvaluationRunState.PASSED
        now = _utc_now()
        return await self._repository.update_run(
            run.model_copy(
                update={
                    "state": state,
                    "passed_case_runs": passed,
                    "failed_case_runs": failed,
                    "error_case_runs": errors,
                    "canceled_case_runs": canceled,
                    "average_score": average_score,
                    "average_duration_ms": average_duration_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "billing_quantity": billing_quantity,
                    "finished_at": now,
                    "updated_at": now,
                }
            )
        )

    async def _evaluate_gate(self, run: EvaluationRun) -> EvaluationGateResult | None:
        if run.gate_policy_id is None:
            return None
        if run.state == EvaluationRunState.CANCELED:
            return None
        policy = await self._require_gate_policy(run.gate_policy_id)
        if policy.suite_id != run.suite_id or policy.branch_id != run.branch_id:
            raise EvaluationLabValidationError(
                "Gate policy does not match the evaluation run suite and branch"
            )
        metrics, violations = await self._gate_metrics_and_violations(run, policy)
        gate_state = EvaluationGateState.FAILED if violations else EvaluationGateState.PASSED
        result = EvaluationGateResult(
            gate_result_id=_new_id(),
            run_id=run.run_id,
            gate_policy_id=policy.gate_policy_id,
            state=gate_state,
            metrics=metrics,
            violations=violations,
            created_at=_utc_now(),
        )
        result = await self._repository.create_gate_result(result)
        updated_run = run.model_copy(update={"gate_state": gate_state, "updated_at": _utc_now()})
        _ = await self._repository.update_run(updated_run)
        _ = await self._append_event(
            run.run_id,
            None,
            EvaluationEventType.GATE_EVALUATED,
            {
                "gate_policy_id": policy.gate_policy_id,
                "state": str(gate_state),
                "metrics": metrics,
                "violations": violations,
            },
        )
        return result

    async def _gate_metrics_and_violations(
        self,
        run: EvaluationRun,
        policy: EvaluationGatePolicy,
    ) -> tuple[JsonObject, list[str]]:
        if run.total_case_runs <= 0:
            raise EvaluationLabValidationError("Evaluation run gate requires total_case_runs > 0")
        pass_rate = run.passed_case_runs / run.total_case_runs
        metrics: JsonObject = {
            "pass_rate": pass_rate,
            "average_score": run.average_score,
            "average_duration_ms": run.average_duration_ms,
            "passed_case_runs": run.passed_case_runs,
            "failed_case_runs": run.failed_case_runs,
            "error_case_runs": run.error_case_runs,
            "canceled_case_runs": run.canceled_case_runs,
            "total_case_runs": run.total_case_runs,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": run.total_tokens,
            "billing_quantity": run.billing_quantity,
        }
        violations: list[str] = []
        if pass_rate < policy.min_pass_rate:
            violations.append("pass_rate_below_threshold")
        if run.average_score is None:
            if policy.min_average_score is not None:
                violations.append("average_score_missing")
        elif policy.min_average_score is not None and run.average_score < policy.min_average_score:
            violations.append("average_score_below_threshold")
        if run.failed_case_runs > policy.max_failed_case_runs:
            violations.append("failed_case_runs_above_threshold")
        if run.error_case_runs > policy.max_error_case_runs:
            violations.append("error_case_runs_above_threshold")
        if (
            policy.max_average_duration_ms is not None
            and run.average_duration_ms is not None
            and run.average_duration_ms > policy.max_average_duration_ms
        ):
            violations.append("average_duration_above_threshold")
        if policy.max_average_duration_ms is not None and run.average_duration_ms is None:
            violations.append("average_duration_missing")
        baseline = await self._repository.get_baseline(run.suite_id, run.branch_id)
        if baseline is None:
            if (
                policy.require_baseline
                or policy.min_baseline_score_delta is not None
                or policy.max_baseline_duration_delta_ms is not None
            ):
                violations.append("baseline_missing")
            return metrics, violations
        baseline_run = await self._require_run_model(baseline.run_id)
        if baseline_run.suite_id != run.suite_id or baseline_run.branch_id != run.branch_id:
            raise EvaluationLabValidationError("Stored baseline points to an incompatible run")
        metrics["baseline_run_id"] = baseline_run.run_id
        score_delta = self._run_score_delta(baseline_run, run)
        duration_delta = self._run_duration_delta(baseline_run, run)
        metrics["baseline_score_delta"] = score_delta
        metrics["baseline_duration_delta_ms"] = duration_delta
        if policy.min_baseline_score_delta is not None:
            if score_delta is None:
                violations.append("baseline_score_delta_missing")
            elif score_delta < policy.min_baseline_score_delta:
                violations.append("baseline_score_delta_below_threshold")
        if policy.max_baseline_duration_delta_ms is not None:
            if duration_delta is None:
                violations.append("baseline_duration_delta_missing")
            elif duration_delta > policy.max_baseline_duration_delta_ms:
                violations.append("baseline_duration_delta_above_threshold")
        return metrics, violations

    async def _evaluate_check(
        self,
        *,
        check: EvaluationCheck,
        state: ExecutionState,
        state_json: JsonObject,
        response: str,
        dialog: list[EvaluationDialogMessage],
        usage: LlmUsageAccumulator,
    ) -> CheckOutcome:
        if isinstance(check, EvaluationCheckContains):
            return self._check_contains(check, state_json, response)
        if isinstance(check, EvaluationCheckNotContains):
            return self._check_not_contains(check, state_json, response)
        if isinstance(check, EvaluationCheckRegex):
            return self._check_regex(check, state_json, response)
        if isinstance(check, EvaluationCheckLength):
            return self._check_length(check, state_json, response)
        if isinstance(check, EvaluationCheckStatePath):
            return self._check_state_path(check, state_json)
        if isinstance(check, EvaluationCheckJsonSchema):
            return self._check_json_schema(check, state_json, response)
        if isinstance(check, EvaluationCheckTraceAssertion):
            return await self._check_trace_assertion(check, state)
        if isinstance(check, EvaluationCheckCode):
            return await self._check_code(check, state, state_json, response, dialog)
        if isinstance(check, EvaluationCheckBuiltinMetric):
            return await self._check_builtin_metric(
                check,
                state,
                state_json,
                response,
                dialog,
                usage,
            )
        return await self._check_llm_judge(check, state, state_json, response, dialog, usage)

    def _check_contains(
        self,
        check: EvaluationCheckContains,
        state_json: JsonObject,
        response: str,
    ) -> CheckOutcome:
        haystack = self._source_text(check.source, check.state_path, state_json, response)
        values = self._normalize_strings(check.values, check.case_sensitive)
        target = haystack if check.case_sensitive else haystack.lower()
        if check.mode == EvaluationContainsMode.ALL:
            passed = all(value in target for value in values)
        else:
            passed = any(value in target for value in values)
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    def _check_not_contains(
        self,
        check: EvaluationCheckNotContains,
        state_json: JsonObject,
        response: str,
    ) -> CheckOutcome:
        haystack = self._source_text(check.source, check.state_path, state_json, response)
        values = self._normalize_strings(check.values, check.case_sensitive)
        target = haystack if check.case_sensitive else haystack.lower()
        passed = not any(value in target for value in values)
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    def _check_regex(
        self,
        check: EvaluationCheckRegex,
        state_json: JsonObject,
        response: str,
    ) -> CheckOutcome:
        flags = re.IGNORECASE if check.ignore_case else 0
        target = self._source_text(check.source, check.state_path, state_json, response)
        passed = re.search(check.pattern, target, flags) is not None
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    def _check_length(
        self,
        check: EvaluationCheckLength,
        state_json: JsonObject,
        response: str,
    ) -> CheckOutcome:
        if check.min_chars is None and check.max_chars is None:
            raise EvaluationLabValidationError("length check requires min_chars or max_chars")
        target = self._source_text(check.source, check.state_path, state_json, response)
        length = len(target)
        lower_passed = check.min_chars is None or length >= check.min_chars
        upper_passed = check.max_chars is None or length <= check.max_chars
        passed = lower_passed and upper_passed
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    def _check_state_path(
        self,
        check: EvaluationCheckStatePath,
        state_json: JsonObject,
    ) -> CheckOutcome:
        if check.operator == EvaluationStateOperator.EXISTS:
            passed = self._path_exists(state_json, check.path)
            return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)
        actual = self._read_path(state_json, check.path)
        expected = check.value
        passed = self._compare_state_values(actual, expected, check.operator)
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    def _check_json_schema(
        self,
        check: EvaluationCheckJsonSchema,
        state_json: JsonObject,
        response: str,
    ) -> CheckOutcome:
        target = self._source_value(check.source, check.state_path, state_json, response)
        validator = Draft202012Validator(check.json_schema)
        validate = cast(Callable[[JsonValue], None], validator.validate)
        try:
            validate(target)
        except JsonSchemaValidationError:
            return CheckOutcome(scores={"result": 0.0}, passed=False)
        return CheckOutcome(scores={"result": 10.0}, passed=True)

    async def _check_trace_assertion(
        self,
        check: EvaluationCheckTraceAssertion,
        state: ExecutionState,
    ) -> CheckOutcome:
        records, _ = await self._flow_factory.container.workflow_runtime.get_state_history(
            state.session_id,
            limit=1000,
        )
        passed = False
        for record in records:
            payload = record.payload
            if check.assertion == EvaluationTraceAssertion.NODE_COMPLETED:
                if isinstance(payload, NodeCompletedPayload) and payload.node_id == check.value:
                    passed = True
                    break
            elif check.assertion == EvaluationTraceAssertion.NODE_FAILED:
                if isinstance(payload, NodeFailedPayload) and check.value in payload.failed_nodes:
                    passed = True
                    break
            elif check.assertion == EvaluationTraceAssertion.TOOL_CALLED:
                if isinstance(payload, ActivityLifecyclePayload):
                    if payload.node_id == check.value or payload.tool_call_id == check.value:
                        passed = True
                        break
        return CheckOutcome(scores={"result": 10.0 if passed else 0.0}, passed=passed)

    async def _check_code(
        self,
        check: EvaluationCheckCode,
        state: ExecutionState,
        state_json: JsonObject,
        response: str,
        dialog: list[EvaluationDialogMessage],
    ) -> CheckOutcome:
        runner = self._flow_factory.container.get_code_runner(language=check.language)
        dialog_payload: list[JsonValue] = [
            require_json_object(message.model_dump(mode="json"), "evaluation.dialog[]")
            for message in dialog
        ]
        result = await runner.execute_tool(
            check.source,
            {"state": state_json, "response": response, "dialog": dialog_payload},
            state,
            entrypoint=check.entrypoint,
        )
        scores = self._normalize_scores(result)
        return CheckOutcome(scores=scores, passed=self._scores_passed(scores))

    async def _check_builtin_metric(
        self,
        check: EvaluationCheckBuiltinMetric,
        state: ExecutionState,
        state_json: JsonObject,
        response: str,
        dialog: list[EvaluationDialogMessage],
        usage: LlmUsageAccumulator,
    ) -> CheckOutcome:
        target = self._source_text(check.source, check.state_path, state_json, response)
        threshold = self._builtin_metric_threshold(check)
        if check.evaluator_id == EvaluationBuiltinMetricId.ROUGE_L:
            reference = self._builtin_metric_reference(check)
            score = self._rouge_l_score(target, reference) * 10.0
            passed = score >= threshold
            return CheckOutcome(
                scores={str(check.evaluator_id): score},
                passed=passed,
                feedback=f"ROUGE-L score {score:.3f} against threshold {threshold:.3f}",
            )
        if check.evaluator_id == EvaluationBuiltinMetricId.BLEU:
            reference = self._builtin_metric_reference(check)
            score = self._bleu_score(target, reference) * 10.0
            passed = score >= threshold
            return CheckOutcome(
                scores={str(check.evaluator_id): score},
                passed=passed,
                feedback=f"BLEU score {score:.3f} against threshold {threshold:.3f}",
            )
        return await self._check_llm_builtin_metric(
            check=check,
            state=state,
            state_json=state_json,
            response=response,
            target=target,
            dialog=dialog,
            usage=usage,
            threshold=threshold,
        )

    async def _check_llm_builtin_metric(
        self,
        *,
        check: EvaluationCheckBuiltinMetric,
        state: ExecutionState,
        state_json: JsonObject,
        response: str,
        target: str,
        dialog: list[EvaluationDialogMessage],
        usage: LlmUsageAccumulator,
        threshold: float,
    ) -> CheckOutcome:
        if check.evaluator_id not in LLM_BUILTIN_METRIC_IDS:
            raise EvaluationLabValidationError(
                f"Unsupported builtin metric evaluator: {check.evaluator_id}"
            )
        reference = check.reference
        if check.evaluator_id in REFERENCE_BUILTIN_METRIC_IDS:
            reference = self._builtin_metric_reference(check)
        prompt = await self._builtin_metric_prompt(check, state)
        dialog_text = "\n".join(f"{message.role.upper()}: {message.content}" for message in dialog)
        message = (
            f"{prompt}\n\n"
            f"Evaluator ID: {check.evaluator_id}\n"
            f"Threshold: {threshold}\n"
            f"Reference/context:\n{reference or ''}\n\n"
            f"Latest response:\n{response}\n\n"
            f"Metric target:\n{target}\n\n"
            f"State JSON:\n{json.dumps(state_json, ensure_ascii=False, sort_keys=True)}\n\n"
            f"Dialog:\n{dialog_text}\n\n"
            f"Call the {EVALUATION_BUILTIN_METRIC_TOOL_NAME} tool exactly once."
        )
        metric = await self._invoke_evaluation_llm_tool(
            messages=[{"role": "user", "content": message}],
            tools=[self._builtin_metric_tool()],
            tool_name=EVALUATION_BUILTIN_METRIC_TOOL_NAME,
            task_id=_new_id(),
            context_id=state.context_id,
            llm_context=LLMContextPatch(profile="compact"),
        )
        usage.add(metric.usage)
        result = EvaluationBuiltinMetricJudgeResult.model_validate(metric.arguments)
        return CheckOutcome(
            scores={str(check.evaluator_id): result.score},
            passed=result.passed,
            feedback=result.feedback,
        )

    async def _check_llm_judge(
        self,
        check: EvaluationCheckLlmJudge,
        state: ExecutionState,
        state_json: JsonObject,
        response: str,
        dialog: list[EvaluationDialogMessage],
        usage: LlmUsageAccumulator,
    ) -> CheckOutcome:
        prompt = await self._judge_prompt(check, state)
        rubric_version = await self._require_rubric_version(check.rubric_version_id)
        dialog_text = "\n".join(f"{message.role.upper()}: {message.content}" for message in dialog)
        message = (
            f"{prompt}\n\n"
            f"Rubric version ID: {rubric_version.rubric_version_id}\n"
            f"Rubric version: {rubric_version.version}\n"
            f"Rubric:\n{rubric_version.prompt}\n\n"
            f"Latest response:\n{response}\n\n"
            f"State JSON:\n{json.dumps(state_json, ensure_ascii=False, sort_keys=True)}\n\n"
            f"Dialog:\n{dialog_text}\n\n"
            f"Call the {EVALUATION_JUDGE_TOOL_NAME} tool exactly once with the judgment."
        )
        judgment = await self._invoke_evaluation_llm_tool(
            messages=[{"role": "user", "content": message}],
            tools=[self._llm_judge_tool()],
            tool_name=EVALUATION_JUDGE_TOOL_NAME,
            task_id=_new_id(),
            context_id=state.context_id,
            llm_context=LLMContextPatch(profile="compact"),
        )
        usage.add(judgment.usage)
        judge_result = EvaluationLlmJudgeResult.model_validate(judgment.arguments)
        scores = judge_result.scores
        if not scores:
            if judge_result.total_score is None:
                raise EvaluationLabValidationError(
                    "llm_judge response requires scores or total_score"
                )
            scores = {"result": judge_result.total_score}
        total = self._total_score(scores)
        assert total is not None
        passed = judge_result.passed
        if passed is None:
            passed = total >= rubric_version.pass_threshold
        return CheckOutcome(scores=scores, passed=passed, feedback=judge_result.feedback)

    async def _input_to_text(
        self,
        input_config: EvaluationInput,
        state: ExecutionState,
        dialog: list[EvaluationDialogMessage],
        usage: LlmUsageAccumulator,
    ) -> str:
        if isinstance(input_config, EvaluationInputText):
            return input_config.content
        if isinstance(input_config, EvaluationInputInlineCode):
            runner = self._flow_factory.container.get_code_runner(language=input_config.language)
            result = await runner.execute_tool(
                input_config.source,
                {},
                state,
                entrypoint=input_config.entrypoint,
            )
            return _json_string(result)
        node_config = await self._resolve_input_node(input_config, state)
        dialog_text = "\n".join(
            f"{message.role.upper()}: {message.content}" for message in dialog
        )
        prompt = node_config.prompt
        if prompt is None or not prompt.strip():
            prompt = "Generate the next user message for this evaluation case."
        result = await self._invoke_evaluation_llm(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Dialog so far:\n{dialog_text}"},
            ],
            task_id=_new_id(),
            context_id=state.context_id,
            llm_context=node_config.llm_context or LLMContextPatch(profile="compact"),
        )
        usage.add(result.usage)
        return result.content

    async def _create_target_runtime(
        self,
        case: EvaluationCase,
        branch_id: str,
        flow_config_version: str,
    ) -> TargetRuntime:
        if not flow_config_version.strip():
            raise EvaluationLabValidationError("flow_config_version must be non-empty")
        if isinstance(case.target, EvaluationTargetFlow):
            target_flow_id = case.target.flow_id if case.target.flow_id is not None else case.flow_id
            target_branch_id = (
                case.target.branch_id if case.target.branch_id is not None else branch_id
            )
            target_flow_config_version = flow_config_version
            if target_flow_id != case.flow_id:
                target_flow = await self._flow_repository.get(target_flow_id)
                if target_flow is None:
                    raise EvaluationLabNotFoundError(f"Flow not found: {target_flow_id}")
                target_flow_config_version = target_flow.version.strip()
                if not target_flow_config_version:
                    raise EvaluationLabValidationError(
                        f"Flow has no persisted config version: {target_flow_id}"
                    )
            runtime_flow = await self._flow_factory.get_flow(
                target_flow_id,
                target_branch_id,
                target_flow_config_version,
            )
            if runtime_flow is None:
                raise EvaluationLabNotFoundError(f"Flow not found: {target_flow_id}")

            async def run_flow(state: ExecutionState) -> ExecutionState:
                state.flow_config_version = target_flow_config_version
                state.branch_id = target_branch_id
                await self._start_evaluation_workflow(
                    state,
                    flow_id=target_flow_id,
                    branch_id=target_branch_id,
                )
                return await runtime_flow.run(state)

            return TargetRuntime(
                callable=run_flow,
                flow_id=target_flow_id,
                branch_id=target_branch_id,
                flow_config_version=target_flow_config_version,
            )
        node_config = NodeConfig.model_validate(case.target.node)
        node_class = self._node_registry.get(node_config.type)
        node = node_class.from_config(
            node_config.node_id,
            node_config.model_dump(mode="json"),
            container=self._flow_factory.container,
        )

        async def run_node(state: ExecutionState) -> ExecutionState:
            state.flow_config_version = flow_config_version
            await self._start_evaluation_workflow(
                state,
                flow_id=case.flow_id,
                branch_id=branch_id,
            )
            state.current_nodes = [node_config.node_id]
            runtime = self._flow_factory.container.workflow_runtime
            superstep_event = await runtime.record_state_event(
                state.session_id,
                state,
                event_type=WorkflowEventType.superstep_started,
                payload=SuperstepStartedPayload(current_nodes=[node_config.node_id]),
            )
            scheduled_event = await runtime.record_state_event(
                state.session_id,
                state,
                event_type=WorkflowEventType.node_scheduled,
                payload=NodeScheduledPayload(
                    node_id=node_config.node_id,
                    node_type=node_config.type.value,
                    current_nodes=[node_config.node_id],
                ),
            )
            state.attach_durable_node_context(
                execution_branch_id=scheduled_event.execution_branch_id,
                node_schedule_sequence=scheduled_event.sequence,
                superstep_sequence=superstep_event.sequence,
            )
            before_state = state.runtime_copy()
            result_state = await node.run(state)
            _ = await runtime.record_state_event(
                result_state.session_id,
                result_state,
                event_type=WorkflowEventType.node_write_recorded,
                payload=NodeWriteRecordedPayload(
                    node_id=node_config.node_id,
                    node_type=node_config.type.value,
                    state_delta=build_state_delta(before_state, result_state),
                ),
            )
            _ = await runtime.record_state_event(
                result_state.session_id,
                result_state,
                event_type=WorkflowEventType.node_completed,
                payload=NodeCompletedPayload(
                    node_id=node_config.node_id,
                    node_type=node_config.type.value,
                ),
            )
            return result_state

        return TargetRuntime(
            callable=run_node,
            flow_id=case.flow_id,
            branch_id=branch_id,
            flow_config_version=flow_config_version,
        )

    def _create_execution_state(
        self,
        *,
        case: EvaluationCase,
        target_runtime: TargetRuntime,
        task_id: str,
        context_id: str,
        session_id: str,
    ) -> ExecutionState:
        initial_state = dict(case.initial_state) if case.initial_state is not None else {}
        return ExecutionState.model_validate(
            {
                **initial_state,
                "task_id": task_id,
                "context_id": context_id,
                "session_id": session_id,
                "user_id": "evaluation_lab",
                "content": "",
                "branch_id": target_runtime.branch_id,
                "flow_config_version": target_runtime.flow_config_version,
            }
        )

    async def _start_evaluation_workflow(
        self,
        state: ExecutionState,
        *,
        flow_id: str,
        branch_id: str,
    ) -> None:
        if state.session_flow_id != flow_id:
            raise RuntimeError(
                "Evaluation workflow session_id must target evaluated flow: "
                + f"flow_id={flow_id!r}, session_id={state.session_id!r}"
            )
        if state.flow_config_version is None or not state.flow_config_version.strip():
            raise EvaluationLabValidationError("evaluation state requires flow_config_version")
        runtime = self._flow_factory.container.workflow_runtime
        position = await runtime.get_active_execution_position(state.session_id)
        if position is not None:
            return
        state.branch_id = branch_id
        _ = await runtime.record_state_event(
            state.session_id,
            state,
            event_type=WorkflowEventType.run_started,
            payload=RunStartedPayload(
                flow_id=flow_id,
                branch_id=branch_id,
                task_id=state.task_id,
                flow_config_version=state.flow_config_version,
            ),
            snapshot=True,
        )

    async def _select_cases(
        self,
        *,
        suite_id: str,
        branch_id: str,
        scope: EvaluationRunScope,
    ) -> list[EvaluationCase]:
        cases = await self._repository.list_cases(suite_id)
        matching_cases = [case for case in cases if self._case_matches_branch(case, branch_id)]
        if isinstance(scope, EvaluationRunSuiteScope):
            return [case for case in matching_cases if case.enabled]
        by_id = {case.case_id: case for case in matching_cases}
        selected: list[EvaluationCase] = []
        for case_id in scope.case_ids:
            if case_id not in by_id:
                raise EvaluationLabNotFoundError(
                    f"Evaluation case not found in branch scope: {case_id}"
                )
            case = by_id[case_id]
            if not case.enabled:
                raise EvaluationLabValidationError(f"Evaluation case is disabled: {case_id}")
            selected.append(case)
        return selected

    def _case_matches_branch(self, case: EvaluationCase, branch_id: str) -> bool:
        if case.branch_ids == "*":
            return True
        return branch_id in case.branch_ids

    def _parse_jsonl_case_import(self, content: str) -> list[EvaluationCaseCreateRequest]:
        requests: list[EvaluationCaseCreateRequest] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                raise EvaluationLabValidationError(
                    f"evaluation case JSONL line {line_number} must not be empty"
                )
            try:
                requests.append(EvaluationCaseCreateRequest.model_validate_json(line))
            except ValueError as exc:
                raise EvaluationLabValidationError(
                    f"evaluation case JSONL line {line_number} is invalid"
                ) from exc
        if not requests:
            raise EvaluationLabValidationError("evaluation case JSONL import is empty")
        return requests

    def _parse_csv_case_import(self, content: str) -> list[EvaluationCaseCreateRequest]:
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None:
            raise EvaluationLabValidationError("evaluation case CSV import requires a header")
        allowed_fields = {
            "name",
            "description",
            "branch_ids_json",
            "target_json",
            "initial_state_json",
            "turns_json",
            "max_turns",
            "timeout_seconds",
            "enabled",
            "tags_json",
            "sort_order",
        }
        required_fields = {"name", "branch_ids_json", "turns_json"}
        fields = set(reader.fieldnames)
        missing = sorted(required_fields.difference(fields))
        if missing:
            raise EvaluationLabValidationError(
                "evaluation case CSV missing required columns: " + ", ".join(missing)
            )
        extra = sorted(fields.difference(allowed_fields))
        if extra:
            raise EvaluationLabValidationError(
                "evaluation case CSV has unsupported columns: " + ", ".join(extra)
            )
        requests: list[EvaluationCaseCreateRequest] = []
        for row_number, row in enumerate(reader, start=2):
            requests.append(self._case_request_from_csv_row(row, row_number))
        if not requests:
            raise EvaluationLabValidationError("evaluation case CSV import is empty")
        return requests

    def _case_request_from_csv_row(
        self,
        row: dict[str, str | None],
        row_number: int,
    ) -> EvaluationCaseCreateRequest:
        payload: JsonObject = {
            "name": self._csv_required_string(row, "name", row_number),
            "branch_ids": self._csv_branch_ids(row, row_number),
            "turns": self._csv_turns(row, row_number),
        }
        description = self._csv_optional_string(row, "description", row_number)
        if description is not None:
            payload["description"] = description
        target = self._csv_optional_object(row, "target_json", row_number)
        if target is not None:
            payload["target"] = target
        initial_state = self._csv_optional_object(row, "initial_state_json", row_number)
        if initial_state is not None:
            payload["initial_state"] = initial_state
        max_turns = self._csv_optional_int(row, "max_turns", row_number)
        if max_turns is not None:
            payload["max_turns"] = max_turns
        timeout_seconds = self._csv_optional_int(row, "timeout_seconds", row_number)
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        enabled = self._csv_optional_bool(row, "enabled", row_number)
        if enabled is not None:
            payload["enabled"] = enabled
        tags = self._csv_optional_string_list(row, "tags_json", row_number)
        if tags is not None:
            payload["tags"] = tags
        sort_order = self._csv_optional_int(row, "sort_order", row_number)
        if sort_order is not None:
            payload["sort_order"] = sort_order
        return EvaluationCaseCreateRequest.model_validate(payload)

    def _csv_required_string(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> str:
        value = row[field_name]
        if value is None or not value.strip():
            raise EvaluationLabValidationError(
                f"evaluation case CSV row {row_number} field {field_name} is required"
            )
        return value.strip()

    def _csv_optional_string(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> str | None:
        if field_name not in row:
            return None
        value = row[field_name]
        if value is None or value == "":
            return None
        if not value.strip():
            raise EvaluationLabValidationError(
                f"evaluation case CSV row {row_number} field {field_name} must not be blank"
            )
        return value.strip()

    def _csv_optional_int(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> int | None:
        value = self._csv_optional_string(row, field_name, row_number)
        if value is None:
            return None
        if not value.isdecimal():
            raise EvaluationLabValidationError(
                f"evaluation case CSV row {row_number} field {field_name} must be an integer"
            )
        return int(value)

    def _csv_optional_bool(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> bool | None:
        value = self._csv_optional_string(row, field_name, row_number)
        if value is None:
            return None
        if value == "true":
            return True
        if value == "false":
            return False
        raise EvaluationLabValidationError(
            f"evaluation case CSV row {row_number} field {field_name} must be true or false"
        )

    def _csv_optional_object(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> JsonObject | None:
        value = self._csv_optional_string(row, field_name, row_number)
        if value is None:
            return None
        try:
            return parse_json_object(value, f"evaluation case CSV row {row_number}.{field_name}")
        except ValueError as exc:
            raise EvaluationLabValidationError(str(exc)) from exc

    def _csv_optional_string_list(
        self,
        row: dict[str, str | None],
        field_name: str,
        row_number: int,
    ) -> list[str] | None:
        value = self._csv_optional_string(row, field_name, row_number)
        if value is None:
            return None
        return self._string_list_from_json(value, f"evaluation case CSV row {row_number}.{field_name}")

    def _csv_branch_ids(self, row: dict[str, str | None], row_number: int) -> Literal["*"] | list[str]:
        value = self._csv_required_string(row, "branch_ids_json", row_number)
        if value == "*":
            return "*"
        return self._string_list_from_json(value, f"evaluation case CSV row {row_number}.branch_ids_json")

    def _csv_turns(self, row: dict[str, str | None], row_number: int) -> list[JsonValue]:
        value = self._csv_required_string(row, "turns_json", row_number)
        try:
            return parse_json_array(value, f"evaluation case CSV row {row_number}.turns_json")
        except ValueError as exc:
            raise EvaluationLabValidationError(str(exc)) from exc

    def _string_list_from_json(self, value: str, field_name: str) -> list[str]:
        try:
            array = parse_json_array(value, field_name)
        except ValueError as exc:
            raise EvaluationLabValidationError(str(exc)) from exc
        result: list[str] = []
        for index, item in enumerate(array):
            if not isinstance(item, str) or not item.strip():
                raise EvaluationLabValidationError(
                    f"{field_name}[{index}] must be a non-empty string"
                )
            result.append(item.strip())
        return result

    def _dialog_to_turns(
        self,
        dialog: list[EvaluationDialogMessage],
        checks: list[EvaluationCheck],
    ) -> list[EvaluationTurn]:
        turns: list[EvaluationTurn] = []
        for message in dialog:
            if message.role in {"user", "tester"}:
                turns.append(
                    EvaluationTurn(
                        input=EvaluationInputText(type="text", content=message.content),
                        checks=[],
                    )
                )
        if not turns:
            raise EvaluationLabValidationError(
                "Evaluation dialog curation requires at least one user or tester message"
            )
        if checks:
            last_turn = turns[-1]
            turns[-1] = last_turn.model_copy(update={"checks": checks})
        return turns

    async def _require_suite(self, suite_id: str) -> EvaluationSuite:
        suite = await self._repository.get_suite(suite_id)
        if suite is None:
            raise EvaluationLabNotFoundError(f"Evaluation suite not found: {suite_id}")
        return suite

    async def _require_run_model(self, run_id: str) -> EvaluationRun:
        run = await self._repository.get_run(run_id)
        if run is None:
            raise EvaluationLabNotFoundError(f"Evaluation run not found: {run_id}")
        return run

    async def _require_suite_version(self, suite_version_id: str) -> EvaluationSuiteVersion:
        suite_version = await self._repository.get_suite_version(suite_version_id)
        if suite_version is None:
            raise EvaluationLabNotFoundError(
                f"Evaluation suite version not found: {suite_version_id}"
            )
        return suite_version

    async def _require_case(self, suite_id: str, case_id: str) -> EvaluationCase:
        case = await self._repository.get_case(suite_id, case_id)
        if case is None:
            raise EvaluationLabNotFoundError(f"Evaluation case not found: {case_id}")
        return case

    async def _require_rubric(self, rubric_id: str) -> EvaluationRubric:
        rubric = await self._repository.get_rubric(rubric_id)
        if rubric is None:
            raise EvaluationLabNotFoundError(f"Evaluation rubric not found: {rubric_id}")
        return rubric

    async def _require_rubric_version(
        self,
        rubric_version_id: str,
    ) -> EvaluationRubricVersion:
        rubric_version = await self._repository.get_rubric_version(rubric_version_id)
        if rubric_version is None:
            raise EvaluationLabNotFoundError(
                f"Evaluation rubric version not found: {rubric_version_id}"
            )
        return rubric_version

    async def _require_gate_policy(self, gate_policy_id: str) -> EvaluationGatePolicy:
        policy = await self._repository.get_gate_policy(gate_policy_id)
        if policy is None:
            raise EvaluationLabNotFoundError(f"Evaluation gate policy not found: {gate_policy_id}")
        return policy

    async def _require_monitor(self, monitor_id: str) -> EvaluationMonitor:
        monitor = await self._repository.get_monitor(monitor_id)
        if monitor is None:
            raise EvaluationLabNotFoundError(f"Evaluation monitor not found: {monitor_id}")
        return monitor

    async def _require_monitor_observation(
        self,
        monitor_id: str,
        trace_id: str,
    ) -> EvaluationMonitorObservation:
        observation = await self._repository.get_monitor_observation(monitor_id, trace_id)
        if observation is None:
            raise EvaluationLabNotFoundError(
                f"Evaluation monitor observation not found: {trace_id}"
            )
        return observation

    async def _require_annotation(self, annotation_id: str) -> EvaluationAnnotation:
        annotation = await self._repository.get_annotation(annotation_id)
        if annotation is None:
            raise EvaluationLabNotFoundError(f"Evaluation annotation not found: {annotation_id}")
        return annotation

    async def _require_case_run(self, case_run_id: str) -> EvaluationCaseRun:
        case_run = await self._repository.get_case_run(case_run_id)
        if case_run is None:
            raise EvaluationLabNotFoundError(f"Evaluation case run not found: {case_run_id}")
        return case_run

    async def _require_trace(self, trace_id: str) -> list[TraceSpanRecord]:
        spans = await self._span_repository.get_trace(trace_id)
        if not spans:
            raise EvaluationLabNotFoundError(f"Trace not found: {trace_id}")
        return spans

    def _validate_pairwise_case_runs(
        self,
        left: EvaluationCaseRun,
        right: EvaluationCaseRun,
    ) -> None:
        if left.case_run_id == right.case_run_id:
            raise EvaluationLabValidationError(
                "Pairwise judgment requires two different case runs"
            )
        if left.suite_id != right.suite_id:
            raise EvaluationLabValidationError("Pairwise case runs must belong to one suite")
        if left.flow_id != right.flow_id:
            raise EvaluationLabValidationError("Pairwise case runs must belong to one flow")
        if left.branch_id != right.branch_id:
            raise EvaluationLabValidationError("Pairwise case runs must belong to one branch")
        if left.case_id != right.case_id:
            raise EvaluationLabValidationError("Pairwise case runs must evaluate the same case")
        terminal_states = {
            EvaluationCaseRunState.PASSED,
            EvaluationCaseRunState.FAILED,
            EvaluationCaseRunState.ERROR,
            EvaluationCaseRunState.CANCELED,
        }
        if left.state not in terminal_states or right.state not in terminal_states:
            raise EvaluationLabValidationError("Pairwise case runs must be terminal")

    async def _run_is_canceled(self, run_id: str) -> bool:
        run = await self._require_run_model(run_id)
        return run.state == EvaluationRunState.CANCELED

    def _case_run_by_id(
        self,
        case_runs: list[EvaluationCaseRun],
        case_run_id: str,
    ) -> EvaluationCaseRun:
        for case_run in case_runs:
            if case_run.case_run_id == case_run_id:
                return case_run
        raise EvaluationLabNotFoundError(f"Evaluation case run not found: {case_run_id}")

    async def _run_id_for_case_run(self, case_run_id: str) -> str:
        case_run = await self._repository.get_case_run(case_run_id)
        if case_run is None:
            raise EvaluationLabNotFoundError(f"Evaluation case run not found: {case_run_id}")
        return case_run.run_id

    def _current_user_id(self) -> str:
        context = get_context()
        if context is None or not str(context.user.user_id).strip():
            raise EvaluationLabValidationError("user context is required")
        return str(context.user.user_id).strip()

    def _current_trace_id(self) -> str | None:
        trace_context = get_current_trace_context()
        if trace_context is not None:
            raw_trace_id = trace_context.get("trace_id")
            if not isinstance(raw_trace_id, str) or not raw_trace_id.strip():
                raise EvaluationLabValidationError("trace context trace_id must be a non-empty string")
            return raw_trace_id.strip()
        context = get_context()
        if context is None or context.trace_id is None:
            return None
        if not context.trace_id.strip():
            raise EvaluationLabValidationError("context trace_id must be a non-empty string")
        return context.trace_id.strip()

    async def _append_event(
        self,
        run_id: str,
        case_run_id: str | None,
        event_type: EvaluationEventType,
        payload: JsonObject,
    ) -> EvaluationRunEvent:
        lock = self._event_locks.get(run_id)
        if lock is None:
            lock = asyncio.Lock()
            self._event_locks[run_id] = lock
        async with lock:
            event = EvaluationRunEvent(
                event_id=_new_id(),
                run_id=run_id,
                case_run_id=case_run_id,
                sequence=await self._repository.next_event_sequence(run_id),
                event_type=event_type,
                payload=payload,
                created_at=_utc_now(),
            )
            event = await self._repository.append_event(event)
        event_payload = require_json_object(
            event.model_dump(mode="json"),
            "evaluation_run_event",
        )
        await publish_ui_event_to_company(
            require_active_company().company_id,
            FLOWS_EVALUATION_EVENT_RECORDED,
            event_payload,
            correlation_id=run_id,
        )
        return event

    def _source_text(
        self,
        source: EvaluationCheckSource,
        state_path: str | None,
        state_json: JsonObject,
        response: str,
    ) -> str:
        value = self._source_value(source, state_path, state_json, response)
        return _json_string(value)

    def _source_value(
        self,
        source: EvaluationCheckSource,
        state_path: str | None,
        state_json: JsonObject,
        response: str,
    ) -> JsonValue:
        if source == EvaluationCheckSource.RESPONSE:
            if state_path is not None:
                raise EvaluationLabValidationError(
                    "response-sourced check must not define state_path"
                )
            return response
        if state_path is None:
            return state_json
        return self._read_path(state_json, state_path)

    def _normalize_strings(self, values: list[str], case_sensitive: bool) -> list[str]:
        if case_sensitive:
            return values
        return [value.lower() for value in values]

    def _builtin_metric_threshold(self, check: EvaluationCheckBuiltinMetric) -> float:
        if check.threshold is not None:
            return check.threshold
        return BUILTIN_METRIC_DEFAULT_THRESHOLDS[check.evaluator_id]

    def _builtin_metric_reference(self, check: EvaluationCheckBuiltinMetric) -> str:
        if check.reference is None or not check.reference.strip():
            raise EvaluationLabValidationError(
                f"Builtin metric {check.evaluator_id} requires reference"
            )
        return check.reference

    def _metric_tokens(self, value: str) -> list[str]:
        return re.findall(r"[\w]+", value.lower(), flags=re.UNICODE)

    def _rouge_l_score(self, candidate: str, reference: str) -> float:
        candidate_tokens = self._metric_tokens(candidate)
        reference_tokens = self._metric_tokens(reference)
        if not candidate_tokens or not reference_tokens:
            return 0.0
        lcs = self._lcs_length(candidate_tokens, reference_tokens)
        precision = lcs / len(candidate_tokens)
        recall = lcs / len(reference_tokens)
        if precision == 0.0 or recall == 0.0:
            return 0.0
        return (2.0 * precision * recall) / (precision + recall)

    def _lcs_length(self, left: list[str], right: list[str]) -> int:
        previous = [0] * (len(right) + 1)
        for left_token in left:
            current = [0]
            for index, right_token in enumerate(right, start=1):
                if left_token == right_token:
                    current.append(previous[index - 1] + 1)
                else:
                    current.append(max(previous[index], current[index - 1]))
            previous = current
        return previous[-1]

    def _bleu_score(self, candidate: str, reference: str) -> float:
        candidate_tokens = self._metric_tokens(candidate)
        reference_tokens = self._metric_tokens(reference)
        if not candidate_tokens or not reference_tokens:
            return 0.0
        max_order = min(4, len(candidate_tokens))
        precisions: list[float] = []
        for order in range(1, max_order + 1):
            candidate_counts = self._ngram_counts(candidate_tokens, order)
            reference_counts = self._ngram_counts(reference_tokens, order)
            overlap = 0
            total = 0
            for ngram, count in candidate_counts.items():
                total += count
                reference_count = reference_counts[ngram] if ngram in reference_counts else 0
                overlap += min(count, reference_count)
            if total == 0:
                precisions.append(0.0)
            else:
                precisions.append((overlap + 1.0) / (total + 1.0))
        if not precisions:
            return 0.0
        log_precision = sum(math.log(precision) for precision in precisions) / len(precisions)
        brevity_penalty = (
            1.0
            if len(candidate_tokens) > len(reference_tokens)
            else math.exp(1.0 - (len(reference_tokens) / len(candidate_tokens)))
        )
        return brevity_penalty * math.exp(log_precision)

    def _ngram_counts(self, tokens: list[str], order: int) -> dict[tuple[str, ...], int]:
        counts: dict[tuple[str, ...], int] = {}
        for index in range(0, len(tokens) - order + 1):
            ngram = tuple(tokens[index : index + order])
            counts[ngram] = counts[ngram] + 1 if ngram in counts else 1
        return counts

    def _path_exists(self, value: JsonValue, path: str) -> bool:
        try:
            _ = self._read_path(value, path)
            return True
        except EvaluationLabValidationError:
            return False

    def _read_path(self, value: JsonValue, path: str) -> JsonValue:
        current = value
        for key in path.split("."):
            if isinstance(current, dict):
                if key not in current:
                    raise EvaluationLabValidationError(f"State path does not exist: {path}")
                current = current[key]
            elif isinstance(current, list):
                index = self._parse_path_index(key, path)
                if index >= len(current):
                    raise EvaluationLabValidationError(f"State path index does not exist: {path}")
                current = current[index]
            else:
                raise EvaluationLabValidationError(f"State path is not traversable: {path}")
        return current

    def _parse_path_index(self, raw: str, path: str) -> int:
        if not raw.isdecimal():
            raise EvaluationLabValidationError(f"State path list index must be numeric: {path}")
        return int(raw)

    def _compare_state_values(
        self,
        actual: JsonValue,
        expected: JsonValue,
        operator: EvaluationStateOperator,
    ) -> bool:
        if operator == EvaluationStateOperator.EQ:
            return actual == expected
        if operator == EvaluationStateOperator.NE:
            return actual != expected
        if not isinstance(actual, (int, float, str)) or isinstance(actual, bool):
            return False
        if not isinstance(expected, (int, float, str)) or isinstance(expected, bool):
            return False
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return self._compare_numbers(float(actual), float(expected), operator)
        if isinstance(actual, str) and isinstance(expected, str):
            return self._compare_strings(actual, expected, operator)
        return False

    def _compare_numbers(
        self,
        actual: float,
        expected: float,
        operator: EvaluationStateOperator,
    ) -> bool:
        if operator == EvaluationStateOperator.GT:
            return actual > expected
        if operator == EvaluationStateOperator.GTE:
            return actual >= expected
        if operator == EvaluationStateOperator.LT:
            return actual < expected
        if operator == EvaluationStateOperator.LTE:
            return actual <= expected
        raise EvaluationLabValidationError(f"Unsupported state operator: {operator}")

    def _compare_strings(
        self,
        actual: str,
        expected: str,
        operator: EvaluationStateOperator,
    ) -> bool:
        if operator == EvaluationStateOperator.GT:
            return actual > expected
        if operator == EvaluationStateOperator.GTE:
            return actual >= expected
        if operator == EvaluationStateOperator.LT:
            return actual < expected
        if operator == EvaluationStateOperator.LTE:
            return actual <= expected
        raise EvaluationLabValidationError(f"Unsupported state operator: {operator}")

    def _normalize_scores(self, result: JsonValue) -> EvaluationScores:
        if isinstance(result, bool):
            return {"result": result}
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            return {"result": float(result)}
        if isinstance(result, dict):
            scores: EvaluationScores = {}
            for key, value in result.items():
                if isinstance(value, bool):
                    scores[key] = value
                elif isinstance(value, (int, float)):
                    scores[key] = float(value)
                else:
                    raise EvaluationLabValidationError(
                        f"score value must be boolean or number: {key}"
                    )
            if not scores:
                raise EvaluationLabValidationError("score object must not be empty")
            return scores
        raise EvaluationLabValidationError("code check must return boolean, number or score object")

    def _scores_passed(self, scores: EvaluationScores) -> bool:
        for value in scores.values():
            if isinstance(value, bool):
                if not value:
                    return False
            elif value < 5.0:
                return False
        return True

    def _total_score(self, scores: EvaluationScores | None) -> float | None:
        if scores is None:
            return None
        values: list[float] = []
        for value in scores.values():
            if isinstance(value, bool):
                values.append(10.0 if value else 0.0)
            else:
                values.append(value)
        if not values:
            return None
        return sum(values) / len(values)

    def _scores_to_json(self, scores: EvaluationScores) -> JsonObject:
        return {key: value for key, value in scores.items()}

    def _score_delta(
        self,
        left: EvaluationCaseRun | None,
        right: EvaluationCaseRun | None,
    ) -> float | None:
        if left is None or right is None:
            return None
        if left.total_score is None or right.total_score is None:
            return None
        return right.total_score - left.total_score

    def _run_score_delta(self, left: EvaluationRun, right: EvaluationRun) -> float | None:
        if left.average_score is None or right.average_score is None:
            return None
        return right.average_score - left.average_score

    def _duration_delta(
        self,
        left: EvaluationCaseRun | None,
        right: EvaluationCaseRun | None,
    ) -> int | None:
        if left is None or right is None:
            return None
        if left.duration_ms is None or right.duration_ms is None:
            return None
        return right.duration_ms - left.duration_ms

    def _run_duration_delta(self, left: EvaluationRun, right: EvaluationRun) -> float | None:
        if left.average_duration_ms is None or right.average_duration_ms is None:
            return None
        return right.average_duration_ms - left.average_duration_ms

    def _trace_span(self, span: TraceSpanRecord) -> EvaluationTraceSpan:
        return EvaluationTraceSpan(
            span_id=span.span_id,
            trace_id=span.trace_id,
            parent_span_id=span.parent_span_id,
            operation_name=span.operation_name,
            start_time=span.start_time,
            end_time=span.end_time,
            duration_ms=span.duration_ms,
            status=span.status,
            service_name=span.service_name,
            event_type=span.event_type,
            resource_type=span.resource_type,
            resource_id=span.resource_id,
            attributes=span.attributes,
        )

    def _workflow_event(self, record: WorkflowEventRecord) -> EvaluationTraceWorkflowEvent:
        state_delta = require_json_object(
            record.state_delta.model_dump(mode="json"),
            "EvaluationTraceWorkflowEvent.state_delta",
        )
        return EvaluationTraceWorkflowEvent(
            sequence=record.sequence,
            event_type=str(record.event_type),
            payload=workflow_event_payload_json(record.payload),
            state_delta=state_delta,
            created_at=record.created_at,
        )

    def _trace_node_steps(
        self,
        records: list[WorkflowEventRecord],
    ) -> list[EvaluationTraceNodeStep]:
        steps: list[EvaluationTraceNodeStep] = []
        for record in records:
            payload = record.payload
            if isinstance(payload, NodeScheduledPayload):
                steps.append(
                    EvaluationTraceNodeStep(
                        sequence=record.sequence,
                        node_id=payload.node_id,
                        node_type=payload.node_type,
                        status="scheduled",
                    )
                )
            elif isinstance(payload, NodeCompletedPayload):
                steps.append(
                    EvaluationTraceNodeStep(
                        sequence=record.sequence,
                        node_id=payload.node_id,
                        node_type=payload.node_type,
                        status="completed",
                    )
                )
            elif isinstance(payload, NodeFailedPayload):
                for node_id in payload.failed_nodes:
                    steps.append(
                        EvaluationTraceNodeStep(
                            sequence=record.sequence,
                            node_id=node_id,
                            status="failed",
                        )
                    )
        return steps

    def _trace_tool_calls(
        self,
        records: list[WorkflowEventRecord],
    ) -> list[EvaluationTraceToolCall]:
        tool_calls: list[EvaluationTraceToolCall] = []
        for record in records:
            payload = record.payload
            if isinstance(payload, ActivityLifecyclePayload):
                tool_calls.append(
                    EvaluationTraceToolCall(
                        sequence=record.sequence,
                        activity_id=payload.activity_id,
                        activity_type=payload.activity_type,
                        activity_status=str(payload.activity_status),
                        node_id=payload.node_id,
                        tool_call_id=payload.tool_call_id,
                        attempt=payload.attempt,
                        error=payload.error,
                    )
                )
        return tool_calls

    def _trace_state_diffs(
        self,
        records: list[WorkflowEventRecord],
    ) -> list[EvaluationTraceStateDiff]:
        diffs: list[EvaluationTraceStateDiff] = []
        for record in records:
            payload = record.payload
            if isinstance(payload, NodeWriteRecordedPayload):
                state_delta = require_json_object(
                    payload.state_delta.model_dump(mode="json"),
                    "EvaluationTraceStateDiff.state_delta",
                )
                diffs.append(
                    EvaluationTraceStateDiff(
                        sequence=record.sequence,
                        node_id=payload.node_id,
                        node_type=payload.node_type,
                        state_delta=state_delta,
                    )
                )
        return diffs

    def _monitor_trace_is_sampled(self, trace_id: str, sampling_rate: float) -> bool:
        if sampling_rate >= 1.0:
            return True
        if sampling_rate <= 0.0:
            return False
        bucket = zlib.crc32(trace_id.encode("utf-8")) / 0xFFFFFFFF
        return bucket <= sampling_rate

    def _monitor_observation(
        self,
        monitor: EvaluationMonitor,
        trace: TraceSearchResult,
    ) -> EvaluationMonitorObservation:
        now = _utc_now()
        task_id = self._first_trace_task_id(trace.spans)
        session_id = self._first_trace_session_id(trace.spans)
        payload = require_json_object(
            {
            "spans": [span.to_json_object() for span in trace.spans],
            "filter": require_json_object(
                monitor.filter.model_dump(mode="json", exclude_none=True),
                "EvaluationMonitorObservation.filter",
            ),
            },
            "EvaluationMonitorObservation.payload",
        )
        return EvaluationMonitorObservation(
            observation_id=_new_id(),
            monitor_id=monitor.monitor_id,
            suite_id=monitor.suite_id,
            flow_id=monitor.flow_id,
            branch_id=monitor.branch_id,
            trace_id=trace.trace_id,
            task_id=task_id,
            session_id=session_id,
            state=EvaluationMonitorObservationState.SAMPLED,
            span_count=len(trace.spans),
            payload=payload,
            sampled_at=now,
        )

    def _first_trace_task_id(self, spans: list[TraceSpanRecord]) -> str | None:
        for span in spans:
            if span.task_id is not None and span.task_id.strip():
                return span.task_id.strip()
        return None

    def _first_trace_session_id(self, spans: list[TraceSpanRecord]) -> str | None:
        for span in spans:
            if span.session_agent is not None and span.session_agent.strip():
                return span.session_agent.strip()
        return None

    def _elapsed_ms(self) -> Callable[[], int]:
        started = time.perf_counter()

        def elapsed() -> int:
            return int((time.perf_counter() - started) * 1000)

        return elapsed

    async def _resolve_input_node(
        self,
        input_config: EvaluationInputNode,
        state: ExecutionState,
    ) -> NodeConfig:
        if input_config.node is not None:
            return NodeConfig.model_validate(input_config.node)
        if input_config.node_id is None:
            raise EvaluationLabValidationError("node input requires node_id or node")
        return await self._resolve_flow_node(input_config.node_id, state)

    async def _judge_prompt(
        self,
        check: EvaluationCheckLlmJudge,
        state: ExecutionState,
    ) -> str:
        if check.judge_node is not None:
            node_config = NodeConfig.model_validate(check.judge_node)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        if check.judge_node_id is not None:
            node_config = await self._resolve_flow_node(check.judge_node_id, state)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        return "You are a strict evaluator. Score the assistant response against the rubric."

    async def _builtin_metric_prompt(
        self,
        check: EvaluationCheckBuiltinMetric,
        state: ExecutionState,
    ) -> str:
        if check.judge_node is not None:
            node_config = NodeConfig.model_validate(check.judge_node)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        if check.judge_node_id is not None:
            node_config = await self._resolve_flow_node(check.judge_node_id, state)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        return (
            "You are a strict built-in evaluator. Return a calibrated 0-10 score, "
            + "a pass boolean when determinable, and concise feedback."
        )

    async def _judge_pairwise_with_llm(
        self,
        *,
        request: EvaluationPairwiseJudgeRequest,
        left: EvaluationCaseRun,
        right: EvaluationCaseRun,
        rubric_version: EvaluationRubricVersion,
    ) -> EvaluationPairwiseLlmJudgeResult:
        if left.context_id is None:
            raise EvaluationLabValidationError(
                "LLM pairwise judgment requires left case run context_id"
            )
        prompt = await self._pairwise_prompt(request, left)
        message = (
            f"{prompt}\n\n"
            f"Rubric version ID: {rubric_version.rubric_version_id}\n"
            f"Rubric version: {rubric_version.version}\n"
            f"Rubric:\n{rubric_version.prompt}\n\n"
            f"Left case run:\n{json.dumps(left.model_dump(mode='json'), ensure_ascii=False, sort_keys=True)}\n\n"
            f"Right case run:\n{json.dumps(right.model_dump(mode='json'), ensure_ascii=False, sort_keys=True)}\n\n"
            f"Call the {EVALUATION_PAIRWISE_TOOL_NAME} tool exactly once."
        )
        result = await self._invoke_evaluation_llm_tool(
            messages=[{"role": "user", "content": message}],
            tools=[self._pairwise_judge_tool()],
            tool_name=EVALUATION_PAIRWISE_TOOL_NAME,
            task_id=_new_id(),
            context_id=left.context_id,
            llm_context=LLMContextPatch(profile="compact"),
        )
        return EvaluationPairwiseLlmJudgeResult.model_validate(result.arguments)

    async def _pairwise_prompt(
        self,
        request: EvaluationPairwiseJudgeRequest,
        left: EvaluationCaseRun,
    ) -> str:
        if request.judge_node is not None:
            node_config = NodeConfig.model_validate(request.judge_node)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        if request.judge_node_id is not None:
            flow = await self._flow_repository.get(left.flow_id)
            if flow is None:
                raise EvaluationLabNotFoundError(f"Flow not found: {left.flow_id}")
            state = self._case_run_resolution_state(left, flow.version)
            node_config = await self._resolve_flow_node(request.judge_node_id, state)
            if node_config.prompt is not None and node_config.prompt.strip():
                return node_config.prompt
        return (
            "You are a strict pairwise evaluator. Choose left, right, or tie under "
            + "the rubric and return structured scores."
        )

    def _case_run_resolution_state(
        self,
        case_run: EvaluationCaseRun,
        flow_config_version: str,
    ) -> ExecutionState:
        if case_run.task_id is None or case_run.context_id is None or case_run.session_id is None:
            raise EvaluationLabValidationError(
                "Pairwise judge node resolution requires task_id, context_id and session_id"
            )
        return ExecutionState.model_validate(
            {
                "task_id": case_run.task_id,
                "context_id": case_run.context_id,
                "session_id": case_run.session_id,
                "user_id": "evaluation_lab",
                "content": "",
                "branch_id": case_run.branch_id,
                "flow_config_version": flow_config_version,
            }
        )

    async def _resolve_flow_node(self, node_id: str, state: ExecutionState) -> NodeConfig:
        nodes_map = await self._flow_factory.get_effective_nodes_map(
            state.session_flow_id,
            state.branch_id,
            state.flow_config_version,
        )
        if node_id in nodes_map:
            payload = require_json_object(nodes_map[node_id], f"flow.nodes.{node_id}")
            node_payload = dict(payload)
            node_payload["node_id"] = node_id
            return NodeConfig.model_validate(node_payload)
        node_config = await self._node_repository.get(node_id)
        if node_config is not None:
            return node_config
        raise EvaluationLabNotFoundError(f"Evaluation node not found: {node_id}")

    def _llm_judge_tool(self) -> JsonObject:
        return {
            "type": "function",
            "function": {
                "name": EVALUATION_JUDGE_TOOL_NAME,
                "description": "Record a strict evaluation judgment.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "scores": {
                            "type": "object",
                            "additionalProperties": {
                                "oneOf": [{"type": "number"}, {"type": "boolean"}],
                            },
                        },
                        "total_score": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                        "passed": {"type": "boolean"},
                        "feedback": {"type": ["string", "null"]},
                    },
                    "required": ["scores", "total_score", "passed", "feedback"],
                },
            },
        }

    def _builtin_metric_tool(self) -> JsonObject:
        return {
            "type": "function",
            "function": {
                "name": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                "description": "Record a built-in evaluation metric judgment.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "score": {"type": "number", "minimum": 0, "maximum": 10},
                        "passed": {"type": ["boolean", "null"]},
                        "feedback": {"type": ["string", "null"]},
                    },
                    "required": ["score", "passed", "feedback"],
                },
            },
        }

    def _pairwise_judge_tool(self) -> JsonObject:
        return {
            "type": "function",
            "function": {
                "name": EVALUATION_PAIRWISE_TOOL_NAME,
                "description": "Record a strict pairwise evaluation judgment.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "preferred": {"type": "string", "enum": ["left", "right", "tie"]},
                        "scores": {
                            "type": "object",
                            "additionalProperties": {
                                "oneOf": [{"type": "number"}, {"type": "boolean"}],
                            },
                        },
                        "feedback": {"type": "string"},
                    },
                    "required": ["preferred", "scores", "feedback"],
                },
            },
        }

    async def _invoke_evaluation_llm_tool(
        self,
        *,
        messages: list[JsonObject],
        tools: list[JsonObject],
        tool_name: str,
        task_id: str,
        context_id: str,
        llm_context: LLMContextPatch,
    ) -> LlmToolInvocationResult:
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise EvaluationLabValidationError("active company context is required")
        if not str(actx.user.user_id).strip():
            raise EvaluationLabValidationError("user context is required")
        uid = str(actx.user.user_id).strip()
        resolved = resolve_llm_for_capability(
            AICapability.LLM_CHAT,
            include_platform_default=True,
        )
        assert resolved is not None
        llm = create_llm_client(resolved)
        if resolved.cost_origin != COST_ORIGIN_COMPANY:
            await get_billing_service().require_balance_for_billable_operation(
                actx.active_company.company_id,
                uid,
                operation_code=BALANCE_BLOCK_OPERATION_LLM,
                notification_service="flows",
            )
        trace_extra = {
            trace_attributes.ATTR_USER_ID: uid,
            trace_attributes.ATTR_TENANT_COMPANY_ID: actx.active_company.company_id,
        }
        async with traced_operation(
            "flows.evaluation_lab.llm_tool",
            event_type="llm.invoke",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=resolved.billing_resource_name,
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=trace_extra,
        ) as span:
            input_tokens = 0
            output_tokens = 0
            tool_arguments: JsonObject | None = None
            async for event in llm.stream(
                messages=messages,
                tools=tools,
                task_id=task_id,
                context_id=context_id,
                llm_context=llm_context,
            ):
                if not isinstance(event, TaskStatusUpdateEvent):
                    continue
                if event.status.message is None or event.status.message.metadata is None:
                    continue
                metadata = require_json_object(
                    event.status.message.metadata,
                    "evaluation_lab.llm_tool_event.metadata",
                )
                parsed_input_tokens, parsed_output_tokens = _llm_usage_tokens(metadata)
                if parsed_input_tokens is not None:
                    input_tokens = parsed_input_tokens
                if parsed_output_tokens is not None:
                    output_tokens = parsed_output_tokens
                event_tool_arguments = self._tool_call_arguments_from_metadata(
                    metadata,
                    tool_name,
                )
                if event_tool_arguments is not None:
                    if tool_arguments is not None:
                        raise EvaluationLabValidationError(
                            f"evaluation LLM judge called {tool_name} more than once"
                        )
                    tool_arguments = event_tool_arguments
            total_tokens = input_tokens + output_tokens
            billing_quantity = total_tokens if total_tokens > 0 else 1
            span.set_attribute(trace_attributes.ATTR_BILLING_QUANTITY, billing_quantity)
            span.set_attribute(trace_attributes.ATTR_LLM_INPUT_TOKENS, input_tokens)
            span.set_attribute(trace_attributes.ATTR_LLM_OUTPUT_TOKENS, output_tokens)
            if tool_arguments is None:
                raise EvaluationLabValidationError(
                    f"evaluation LLM judge must call {tool_name}"
                )
            return LlmToolInvocationResult(
                arguments=tool_arguments,
                usage=LlmInvocationUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    billing_quantity=billing_quantity,
                ),
            )

    def _tool_call_arguments_from_metadata(
        self,
        metadata: JsonObject,
        tool_name: str,
    ) -> JsonObject | None:
        raw_tool_calls = metadata.get("tool_calls")
        if raw_tool_calls is None:
            return None
        tool_calls = require_json_array(
            raw_tool_calls,
            "evaluation_lab.llm_tool_event.metadata.tool_calls",
        )
        matching_arguments: JsonObject | None = None
        for index, raw_call in enumerate(tool_calls):
            call = require_json_object(
                raw_call,
                f"evaluation_lab.llm_tool_event.metadata.tool_calls[{index}]",
            )
            call_name = self._tool_call_name(
                call,
                f"evaluation_lab.llm_tool_event.metadata.tool_calls[{index}]",
            )
            if call_name != tool_name:
                continue
            arguments = self._tool_call_arguments(
                call,
                f"evaluation_lab.llm_tool_event.metadata.tool_calls[{index}]",
            )
            if matching_arguments is not None:
                raise EvaluationLabValidationError(
                    f"evaluation LLM judge called {tool_name} more than once"
                )
            matching_arguments = arguments
        return matching_arguments

    def _tool_call_name(self, call: JsonObject, field_name: str) -> str:
        top_level_name: str | None = None
        raw_top_level_name = call.get("name")
        if raw_top_level_name is not None:
            if not isinstance(raw_top_level_name, str) or not raw_top_level_name.strip():
                raise EvaluationLabValidationError(f"{field_name}.name must be a non-empty string")
            top_level_name = raw_top_level_name.strip()
        function_name: str | None = None
        function = self._tool_call_function(call, field_name)
        if function is not None:
            raw_function_name = function.get("name")
            if raw_function_name is not None:
                if not isinstance(raw_function_name, str) or not raw_function_name.strip():
                    raise EvaluationLabValidationError(
                        f"{field_name}.function.name must be a non-empty string"
                    )
                function_name = raw_function_name.strip()
        if top_level_name is not None and function_name is not None and top_level_name != function_name:
            raise EvaluationLabValidationError(f"{field_name} has conflicting tool names")
        if top_level_name is not None:
            return top_level_name
        if function_name is not None:
            return function_name
        raise EvaluationLabValidationError(f"{field_name} requires a tool name")

    def _tool_call_arguments(self, call: JsonObject, field_name: str) -> JsonObject:
        top_level_arguments = self._optional_tool_arguments(
            call.get("arguments"),
            f"{field_name}.arguments",
        )
        function = self._tool_call_function(call, field_name)
        function_arguments: JsonObject | None = None
        if function is not None:
            function_arguments = self._optional_tool_arguments(
                function.get("arguments"),
                f"{field_name}.function.arguments",
            )
        if (
            top_level_arguments is not None
            and function_arguments is not None
            and top_level_arguments != function_arguments
        ):
            raise EvaluationLabValidationError(f"{field_name} has conflicting tool arguments")
        if top_level_arguments is not None:
            return top_level_arguments
        if function_arguments is not None:
            return function_arguments
        raise EvaluationLabValidationError(f"{field_name} requires tool arguments")

    def _tool_call_function(self, call: JsonObject, field_name: str) -> JsonObject | None:
        raw_function = call.get("function")
        if raw_function is None:
            return None
        return require_json_object(raw_function, f"{field_name}.function")

    def _optional_tool_arguments(
        self,
        raw_arguments: JsonValue,
        field_name: str,
    ) -> JsonObject | None:
        if raw_arguments is None:
            return None
        if isinstance(raw_arguments, str):
            return parse_json_object(raw_arguments, field_name)
        return require_json_object(raw_arguments, field_name)

    async def _invoke_evaluation_llm(
        self,
        *,
        messages: list[JsonObject],
        task_id: str,
        context_id: str,
        llm_context: LLMContextPatch,
    ) -> LlmTextInvocationResult:
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise EvaluationLabValidationError("active company context is required")
        if not str(actx.user.user_id).strip():
            raise EvaluationLabValidationError("user context is required")
        uid = str(actx.user.user_id).strip()
        resolved = resolve_llm_for_capability(
            AICapability.LLM_CHAT,
            include_platform_default=True,
        )
        assert resolved is not None
        llm = create_llm_client(resolved)
        if resolved.cost_origin != COST_ORIGIN_COMPANY:
            await get_billing_service().require_balance_for_billable_operation(
                actx.active_company.company_id,
                uid,
                operation_code=BALANCE_BLOCK_OPERATION_LLM,
                notification_service="flows",
            )
        trace_extra = {
            trace_attributes.ATTR_USER_ID: uid,
            trace_attributes.ATTR_TENANT_COMPANY_ID: actx.active_company.company_id,
        }
        async with traced_operation(
            "flows.evaluation_lab.llm",
            event_type="llm.invoke",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=resolved.billing_resource_name,
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=trace_extra,
        ) as span:
            content_parts: list[str] = []
            input_tokens = 0
            output_tokens = 0
            async for event in llm.stream(
                messages=messages,
                tools=[],
                task_id=task_id,
                context_id=context_id,
                llm_context=llm_context,
            ):
                if isinstance(event, TaskArtifactUpdateEvent):
                    if event.artifact.parts:
                        for part in event.artifact.parts:
                            if isinstance(part.root, TextPart) and event.artifact.name != "reasoning":
                                content_parts.append(part.root.text)
                    continue
                if event.status.message and event.status.message.metadata:
                    metadata = require_json_object(
                        event.status.message.metadata,
                        "evaluation_lab.llm_event.metadata",
                    )
                    parsed_input_tokens, parsed_output_tokens = _llm_usage_tokens(metadata)
                    if parsed_input_tokens is not None:
                        input_tokens = parsed_input_tokens
                    if parsed_output_tokens is not None:
                        output_tokens = parsed_output_tokens
            total_tokens = input_tokens + output_tokens
            billing_quantity = total_tokens if total_tokens > 0 else 1
            span.set_attribute(trace_attributes.ATTR_BILLING_QUANTITY, billing_quantity)
            span.set_attribute(trace_attributes.ATTR_LLM_INPUT_TOKENS, input_tokens)
            span.set_attribute(trace_attributes.ATTR_LLM_OUTPUT_TOKENS, output_tokens)
            content = "".join(content_parts)
            if not content.strip():
                raise EvaluationLabValidationError("evaluation LLM returned empty content")
            return LlmTextInvocationResult(
                content=content.strip(),
                usage=LlmInvocationUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    billing_quantity=billing_quantity,
                ),
            )
