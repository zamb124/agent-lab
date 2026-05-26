"""E2E tests for the first-class Evaluation Lab API."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Literal

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from taskiq import Context as TaskiqContext
from taskiq.message import TaskiqMessage

import core.tracing.attributes as trace_attr
from apps.flows.src.api.v1.evaluation import _raise_evaluation_error
from apps.flows.src.container import FlowContainer
from apps.flows.src.db.evaluation_lab_repository import EvaluationLabRowValue, _int_scalar
from apps.flows.src.durable_execution import (
    ActivityLifecyclePayload,
    ActivityStatus,
    NodeFailedPayload,
    SideEffectPolicy,
    WorkflowEventType,
)
from apps.flows.src.evaluation.lab_service import (
    EVALUATION_BUILTIN_METRIC_TOOL_NAME,
    EVALUATION_JUDGE_TOOL_NAME,
    EVALUATION_PAIRWISE_TOOL_NAME,
    EvaluationLabNotFoundError,
    EvaluationLabService,
    EvaluationLabValidationError,
    LlmUsageAccumulator,
    _llm_usage_tokens,
)
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.evaluation_lab import (
    EvaluationActiveMonitorCyclesResult,
    EvaluationAnnotation,
    EvaluationAnnotationType,
    EvaluationBaseline,
    EvaluationBaselineComparison,
    EvaluationBuiltinEvaluatorCatalog,
    EvaluationCase,
    EvaluationCaseImportResult,
    EvaluationCaseRun,
    EvaluationCaseRunState,
    EvaluationCaseRunTrace,
    EvaluationCheckContains,
    EvaluationCheckJsonSchema,
    EvaluationCheckLength,
    EvaluationCheckLlmJudge,
    EvaluationCheckNotContains,
    EvaluationCheckRegex,
    EvaluationCheckSource,
    EvaluationCheckStatePath,
    EvaluationCheckTraceAssertion,
    EvaluationContainsMode,
    EvaluationDialogMessage,
    EvaluationEventType,
    EvaluationGatePolicy,
    EvaluationGateResult,
    EvaluationInputNode,
    EvaluationMonitor,
    EvaluationMonitorCycleResult,
    EvaluationMonitorFilter,
    EvaluationMonitorObservation,
    EvaluationMonitorObservationCurationResult,
    EvaluationMonitorObservationState,
    EvaluationMonitorSampleResult,
    EvaluationMonitorState,
    EvaluationPairwiseJudgment,
    EvaluationPairwisePreference,
    EvaluationPendingRunJobsEnqueueResult,
    EvaluationResultsMatrix,
    EvaluationRubric,
    EvaluationRubricWithVersion,
    EvaluationRun,
    EvaluationRunCasesScope,
    EvaluationRunComparison,
    EvaluationRunCreateRequest,
    EvaluationRunEvent,
    EvaluationRunEventsPage,
    EvaluationRunJob,
    EvaluationRunJobState,
    EvaluationRunState,
    EvaluationRunSuiteScope,
    EvaluationRunTrigger,
    EvaluationRunWithCases,
    EvaluationStateOperator,
    EvaluationSuite,
    EvaluationSuiteVersion,
    EvaluationTargetFlow,
    EvaluationTaskiqExecutionContext,
    EvaluationTraceAssertion,
)
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.tasks.task_names import (
    TASK_ENQUEUE_PENDING_EVALUATION_RUNS,
    TASK_EXECUTE_EVALUATION_RUN,
    TASK_RUN_EVALUATION_GATE_POLICY,
    TASK_RUN_EVALUATION_MONITOR_CYCLE,
)
from apps.flows_worker.broker_core import broker as flows_worker_broker
from apps.flows_worker.evaluation_tasks import (
    enqueue_pending_evaluation_runs,
    execute_evaluation_run,
    run_evaluation_gate_policy,
    run_evaluation_monitor_cycle,
)
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.llm_context import LLMContextPatch
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import ListResponse
from core.state import ExecutionState
from core.tracing.models import TraceSpanWrite
from core.types import JsonObject
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.real_taskiq]


def _passing_turns() -> list[JsonObject]:
    return [
        {
            "input": {"type": "text", "content": "ping 42"},
            "checks": [
                {
                    "type": "contains",
                    "values": ["Echo", "42"],
                    "mode": "all",
                },
                {"type": "not_contains", "values": ["fatal"]},
                {"type": "regex", "pattern": "ping\\s+42"},
                {"type": "length", "min_chars": 8, "max_chars": 80},
                {
                    "type": "state_path",
                    "path": "answer",
                    "operator": "eq",
                    "value": "42",
                },
                {
                    "type": "json_schema",
                    "source": "state",
                    "json_schema": {
                        "type": "object",
                        "properties": {"answer": {"const": "42"}},
                        "required": ["answer"],
                    },
                },
                {
                    "type": "trace_assertion",
                    "assertion": "node_completed",
                    "value": "echo",
                },
            ],
        }
    ]


async def _create_code_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Evaluation Lab E2E Flow",
            "entry": "echo",
            "nodes": {
                "echo": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    content = state['content']\n"
                        "    state['answer'] = '42'\n"
                        "    state['response'] = f'Echo: {content} / answer=42'\n"
                        "    return state\n"
                    ),
                }
            },
            "edges": [{"from_node": "echo", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def _create_slow_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Slow Evaluation Lab Flow",
            "entry": "slow",
            "nodes": {
                "slow": {
                    "type": "code",
                    "code": (
                        "import asyncio\n"
                        "async def run(args, state):\n"
                        "    await asyncio.sleep(1.5)\n"
                        "    state['response'] = 'slow done'\n"
                        "    return state\n"
                    ),
                }
            },
            "edges": [{"from_node": "slow", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def _create_suite(client: AsyncClient, flow_id: str, name: str) -> EvaluationSuite:
    response = await client.post(
        "/flows/api/v1/evaluation/suites",
        json={
            "flow_id": flow_id,
            "name": name,
            "description": "Strict evaluation lab suite",
            "tags": ["e2e", "strict"],
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationSuite.model_validate(response.json())


async def _create_rubric(
    client: AsyncClient,
    flow_id: str,
    name: str,
    *,
    prompt: str = "Response must satisfy the rubric.",
    pass_threshold: float = 7.0,
) -> EvaluationRubricWithVersion:
    response = await client.post(
        "/flows/api/v1/evaluation/rubrics",
        json={
            "flow_id": flow_id,
            "name": name,
            "prompt": prompt,
            "pass_threshold": pass_threshold,
            "description": "Strict rubric",
            "tags": ["rubric"],
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationRubricWithVersion.model_validate(response.json())


async def _create_passing_case(client: AsyncClient, suite_id: str, name: str) -> EvaluationCase:
    response = await client.post(
        f"/flows/api/v1/evaluation/suites/{suite_id}/cases",
        json={
            "name": name,
            "description": "Covers deterministic checks and durable trace assertion",
            "branch_ids": "*",
            "turns": _passing_turns(),
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationCase.model_validate(response.json())


async def _wait_for_run(
    client: AsyncClient,
    run_id: str,
    *,
    timeout_seconds: float = 45.0,
) -> EvaluationRunWithCases:
    terminal_states = {
        EvaluationRunState.PASSED,
        EvaluationRunState.FAILED,
        EvaluationRunState.ERROR,
        EvaluationRunState.CANCELED,
    }
    deadline = time.monotonic() + timeout_seconds
    last_payload: EvaluationRunWithCases | None = None
    while time.monotonic() < deadline:
        response = await client.get(f"/flows/api/v1/evaluation/runs/{run_id}")
        assert response.status_code == 200, response.text
        payload = EvaluationRunWithCases.model_validate(response.json())
        last_payload = payload
        if payload.run.state in terminal_states:
            return payload
        await asyncio.sleep(0.2)
    raise AssertionError(f"Evaluation run did not finish: {last_payload}")


async def _wait_for_run_gate_state(
    client: AsyncClient,
    run_id: str,
    *,
    timeout_seconds: float = 45.0,
) -> EvaluationRunWithCases:
    deadline = time.monotonic() + timeout_seconds
    last_payload: EvaluationRunWithCases | None = None
    while time.monotonic() < deadline:
        response = await client.get(f"/flows/api/v1/evaluation/runs/{run_id}")
        assert response.status_code == 200, response.text
        payload = EvaluationRunWithCases.model_validate(response.json())
        last_payload = payload
        if payload.run.gate_state is not None:
            return payload
        await asyncio.sleep(0.2)
    raise AssertionError(f"Evaluation gate state did not appear: {last_payload}")


async def _create_direct_node_case(
    client: AsyncClient,
    suite_id: str,
    name: str,
) -> EvaluationCase:
    response = await client.post(
        f"/flows/api/v1/evaluation/suites/{suite_id}/cases",
        json={
            "name": name,
            "description": "Covers direct node target, inline-code input and sandbox code checks",
            "branch_ids": "*",
            "target": {
                "type": "node",
                "node": {
                    "node_id": "direct_eval_node",
                    "type": "code",
                    "language": "python",
                    "code": (
                        "async def run(args, state):\n"
                        "    content = state['content']\n"
                        "    return {\n"
                        "        'response': f'node target saw {content}',\n"
                        "        'metrics': {\n"
                        "            'score': 9,\n"
                        "            'label': 'green',\n"
                        "            'items': ['alpha', 'beta'],\n"
                        "        },\n"
                        "    }\n"
                    ),
                },
            },
            "turns": [
                {
                    "input": {
                        "type": "inline_code",
                        "language": "python",
                        "source": "async def run(args, state):\n    return 'inline 73'\n",
                    },
                    "checks": [
                        {
                            "type": "contains",
                            "values": ["node target", "inline 73"],
                            "mode": "all",
                        },
                        {
                            "type": "contains",
                            "source": "state",
                            "state_path": "metrics.label",
                            "values": ["green"],
                            "case_sensitive": True,
                        },
                        {
                            "type": "state_path",
                            "path": "metrics.items.1",
                            "operator": "exists",
                        },
                        {
                            "type": "state_path",
                            "path": "metrics.score",
                            "operator": "gte",
                            "value": 9,
                        },
                        {
                            "type": "json_schema",
                            "source": "state",
                            "state_path": "metrics",
                            "json_schema": {
                                "type": "object",
                                "properties": {
                                    "score": {"minimum": 9},
                                    "label": {"const": "green"},
                                    "items": {
                                        "type": "array",
                                        "prefixItems": [
                                            {"const": "alpha"},
                                            {"const": "beta"},
                                        ],
                                    },
                                },
                                "required": ["score", "label", "items"],
                            },
                        },
                        {
                            "type": "code",
                            "language": "python",
                            "source": (
                                "async def run(args, state):\n"
                                "    return {\n"
                                "        'semantic': 9.0,\n"
                                "        'gate': 'inline 73' in args['response'],\n"
                                "    }\n"
                            ),
                        },
                        {
                            "type": "trace_assertion",
                            "assertion": "node_completed",
                            "value": "direct_eval_node",
                        },
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationCase.model_validate(response.json())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _taskiq_context(
    *,
    task_name: str,
    task_id: str,
    labels: dict[str, object],
) -> TaskiqContext:
    return TaskiqContext(
        message=TaskiqMessage(
            task_id=task_id,
            task_name=task_name,
            labels=labels,
            args=[],
            kwargs={},
        ),
        broker=flows_worker_broker,
    )


def _state(flow_id: str, unique_id: str, flow_config_version: str = "test-version") -> ExecutionState:
    return ExecutionState.model_validate(
        {
            "task_id": f"task-{unique_id}",
            "context_id": f"ctx-{unique_id}",
            "session_id": f"{flow_id}:ctx-{unique_id}",
            "user_id": "evaluation_lab_test",
            "content": "",
            "flow_config_version": flow_config_version,
        }
    )


def _trace_span(
    *,
    unique_id: str,
    flow_id: str,
    trace_id: str,
    span_id: str,
    company_id: str,
    user_id: str,
    session_id: str,
) -> TraceSpanWrite:
    now = _now()
    task_id = f"task-monitor-{unique_id}"
    context_id = f"ctx-monitor-{unique_id}"
    return TraceSpanWrite(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation_name=f"flow.{flow_id}",
        kind="INTERNAL",
        start_time=now,
        end_time=now,
        duration_ms=7,
        status="OK",
        service_name="flows",
        company_id=company_id,
        namespace="default",
        user_id=user_id,
        user_name=None,
        user_groups=None,
        session_auth=None,
        session_agent=session_id,
        channel="test",
        event_type="flow.completed",
        resource_type="flow",
        resource_id=flow_id,
        attributes={
            trace_attr.ATTR_FLOW_ID: flow_id,
            trace_attr.ATTR_BRANCH_ID: "default",
            trace_attr.ATTR_TASK_ID: task_id,
            trace_attr.ATTR_CONTEXT_ID: context_id,
            trace_attr.ATTR_NODE_ID: "echo",
        },
        events=[],
    )


def _case(
    *,
    case_id: str,
    suite_id: str,
    flow_id: str,
    branch_ids: Literal["*"] | list[str] = "*",
    enabled: bool = True,
) -> EvaluationCase:
    now = _now()
    return EvaluationCase.model_validate(
        {
            "case_id": case_id,
            "suite_id": suite_id,
            "flow_id": flow_id,
            "name": case_id,
            "branch_ids": branch_ids,
            "turns": [{"input": {"type": "text", "content": "hello"}, "checks": []}],
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }
    )


def _run(
    *,
    run_id: str,
    suite_id: str,
    suite_version_id: str,
    flow_id: str,
    state: EvaluationRunState = EvaluationRunState.QUEUED,
) -> EvaluationRun:
    now = _now()
    return EvaluationRun(
        run_id=run_id,
        suite_id=suite_id,
        suite_version_id=suite_version_id,
        flow_id=flow_id,
        flow_config_version="test-version",
        branch_id="default",
        trigger=EvaluationRunTrigger.MANUAL,
        scope=EvaluationRunSuiteScope(type="suite"),
        state=state,
        total_cases=1,
        trials=1,
        max_concurrency=1,
        total_case_runs=1,
        created_at=now,
        updated_at=now,
    )


def _case_run(
    *,
    case_run_id: str,
    run_id: str,
    case_id: str,
    suite_id: str,
    flow_id: str,
    state: EvaluationCaseRunState = EvaluationCaseRunState.PASSED,
    total_score: float | None = 8.0,
    duration_ms: int | None = 12,
) -> EvaluationCaseRun:
    now = _now()
    return EvaluationCaseRun(
        case_run_id=case_run_id,
        run_id=run_id,
        case_id=case_id,
        trial_index=1,
        suite_id=suite_id,
        flow_id=flow_id,
        branch_id="default",
        state=state,
        task_id=f"task-{case_run_id}",
        context_id=f"ctx-{case_run_id}",
        session_id=f"{flow_id}:ctx-{case_run_id}",
        duration_ms=duration_ms,
        input_tokens=3,
        output_tokens=4,
        total_tokens=7,
        billing_quantity=7,
        turns_count=1,
        scores={"quality": total_score} if total_score is not None else None,
        total_score=total_score,
        dialog=[EvaluationDialogMessage(role="user", content="hello")],
        created_at=now,
        updated_at=now,
    )


class TestEvaluationLabAPI:
    async def test_suite_case_crud_is_persisted(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_crud_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"CRUD suite {unique_id}")
            suite_id = suite.suite_id

            listed = await client.get(
                "/flows/api/v1/evaluation/suites",
                params={"flow_id": flow_id},
            )
            assert listed.status_code == 200, listed.text
            suites = ListResponse[EvaluationSuite].model_validate(listed.json())
            assert suite_id in {item.suite_id for item in suites.items}

            updated = await client.put(
                f"/flows/api/v1/evaluation/suites/{suite_id}",
                json={
                    "name": f"CRUD suite updated {unique_id}",
                    "description": "Updated description",
                    "tags": ["updated"],
                },
            )
            assert updated.status_code == 200, updated.text
            updated_suite = EvaluationSuite.model_validate(updated.json())
            assert updated_suite.description == "Updated description"

            case = await _create_passing_case(client, suite_id, f"CRUD case {unique_id}")
            case_id = case.case_id

            cases = await client.get(f"/flows/api/v1/evaluation/suites/{suite_id}/cases")
            assert cases.status_code == 200, cases.text
            case_list = ListResponse[EvaluationCase].model_validate(cases.json())
            assert [item.case_id for item in case_list.items] == [case_id]

            renamed = await client.put(
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}",
                json={
                    "name": f"CRUD case updated {unique_id}",
                    "description": "Renamed case",
                    "branch_ids": "*",
                    "turns": _passing_turns(),
                    "tags": ["renamed"],
                    "enabled": True,
                    "sort_order": 5,
                },
            )
            assert renamed.status_code == 200, renamed.text
            renamed_case = EvaluationCase.model_validate(renamed.json())
            assert renamed_case.sort_order == 5

            deleted = await client.delete(
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}"
            )
            assert deleted.status_code == 200, deleted.text
            assert deleted.json() == {"deleted": True}

            missing = await client.get(
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}"
            )
            assert missing.status_code == 404
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_target_backend_contracts_cover_imports_rubrics_trials_baselines_and_gates(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_target_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Target suite {unique_id}")
            case = await _create_passing_case(client, suite.suite_id, f"Target case {unique_id}")
            rubric = await _create_rubric(client, flow_id, f"Target rubric {unique_id}")

            rubrics_response = await client.get(
                "/flows/api/v1/evaluation/rubrics",
                params={"flow_id": flow_id},
            )
            assert rubrics_response.status_code == 200, rubrics_response.text
            rubrics = ListResponse[EvaluationRubric].model_validate(rubrics_response.json())
            assert [item.rubric_id for item in rubrics.items] == [rubric.rubric.rubric_id]

            updated_rubric = await client.put(
                f"/flows/api/v1/evaluation/rubrics/{rubric.rubric.rubric_id}",
                json={"name": f"Target rubric updated {unique_id}", "description": "", "tags": []},
            )
            assert updated_rubric.status_code == 200, updated_rubric.text
            assert EvaluationRubric.model_validate(updated_rubric.json()).name.endswith(unique_id)

            version_response = await client.post(
                f"/flows/api/v1/evaluation/rubrics/{rubric.rubric.rubric_id}/versions",
                json={"prompt": "Updated strict rubric.", "pass_threshold": 8.0},
            )
            assert version_response.status_code == 200, version_response.text
            versions_response = await client.get(
                f"/flows/api/v1/evaluation/rubrics/{rubric.rubric.rubric_id}/versions"
            )
            assert versions_response.status_code == 200, versions_response.text
            assert len(versions_response.json()["items"]) == 2

            jsonl_content = json.dumps(
                {
                    "name": f"JSONL import {unique_id}",
                    "branch_ids": ["import-jsonl"],
                    "turns": [{"input": {"type": "text", "content": "jsonl"}}],
                }
            )
            jsonl_import = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/import",
                json={"format": "jsonl", "content": jsonl_content},
            )
            assert jsonl_import.status_code == 200, jsonl_import.text
            assert len(EvaluationCaseImportResult.model_validate(jsonl_import.json()).cases) == 1

            csv_buffer = io.StringIO()
            writer = csv.DictWriter(
                csv_buffer,
                fieldnames=["name", "branch_ids_json", "turns_json", "tags_json"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "name": f"CSV import {unique_id}",
                    "branch_ids_json": json.dumps(["import-csv"]),
                    "turns_json": json.dumps(
                        [{"input": {"type": "text", "content": "csv"}}]
                    ),
                    "tags_json": json.dumps(["csv"]),
                }
            )
            csv_import = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/import",
                json={"format": "csv", "content": csv_buffer.getvalue()},
            )
            assert csv_import.status_code == 200, csv_import.text
            assert len(EvaluationCaseImportResult.model_validate(csv_import.json()).cases) == 1

            dialog_case_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/from-dialog",
                json={
                    "name": f"Dialog curated {unique_id}",
                    "branch_ids": ["dialog"],
                    "dialog": [
                        {"role": "user", "content": "first"},
                        {"role": "assistant", "content": "answer"},
                        {"role": "tester", "content": "second"},
                    ],
                    "checks": [{"type": "contains", "values": ["Echo"]}],
                },
            )
            assert dialog_case_response.status_code == 200, dialog_case_response.text
            dialog_case = EvaluationCase.model_validate(dialog_case_response.json())
            assert len(dialog_case.turns) == 2
            assert dialog_case.turns[-1].checks

            baseline_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert baseline_run_response.status_code == 200, baseline_run_response.text
            baseline_created = EvaluationRunWithCases.model_validate(baseline_run_response.json())
            baseline_payload = await _wait_for_run(client, baseline_created.run.run_id)
            assert baseline_payload.run.state == EvaluationRunState.PASSED

            baseline_response = await client.put(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/baselines/default",
                json={"run_id": baseline_payload.run.run_id},
            )
            assert baseline_response.status_code == 200, baseline_response.text
            baseline = EvaluationBaseline.model_validate(baseline_response.json())
            assert baseline.run_id == baseline_payload.run.run_id

            gate_policy_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/gate-policies",
                json={
                    "branch_id": "default",
                    "name": f"Strict gate {unique_id}",
                    "min_pass_rate": 1.0,
                    "min_average_score": 10.0,
                    "max_failed_case_runs": 0,
                    "max_error_case_runs": 0,
                    "require_baseline": True,
                    "min_baseline_score_delta": 0.0,
                },
            )
            assert gate_policy_response.status_code == 200, gate_policy_response.text
            gate_policy = EvaluationGatePolicy.model_validate(gate_policy_response.json())

            gated_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                    "trials": 2,
                    "max_concurrency": 2,
                    "gate_policy_id": gate_policy.gate_policy_id,
                },
            )
            assert gated_run_response.status_code == 200, gated_run_response.text
            gated_created = EvaluationRunWithCases.model_validate(gated_run_response.json())
            gated_payload = await _wait_for_run_gate_state(client, gated_created.run.run_id)
            assert gated_payload.run.state == EvaluationRunState.PASSED
            assert gated_payload.run.total_cases == 1
            assert gated_payload.run.total_case_runs == 2
            assert gated_payload.run.passed_case_runs == 2
            assert gated_payload.run.gate_state == "passed"
            assert [item.trial_index for item in gated_payload.case_runs] == [1, 2]
            assert all(item.trace_id is not None for item in gated_payload.case_runs)

            gate_result_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{gated_payload.run.run_id}/gate-result"
            )
            assert gate_result_response.status_code == 200, gate_result_response.text
            gate_result = EvaluationGateResult.model_validate(gate_result_response.json())
            assert gate_result.state == "passed"
            assert gate_result.violations == []

            baselines_response = await client.get(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/baselines"
            )
            assert baselines_response.status_code == 200, baselines_response.text
            baselines = ListResponse[EvaluationBaseline].model_validate(baselines_response.json())
            assert [item.run_id for item in baselines.items] == [baseline.run_id]

            curated_from_run_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/from-case-run",
                json={
                    "name": f"Curated from run {unique_id}",
                    "case_run_id": gated_payload.case_runs[0].case_run_id,
                    "checks": [{"type": "contains", "values": ["Echo"]}],
                },
            )
            assert curated_from_run_response.status_code == 200, curated_from_run_response.text
            curated_from_run = EvaluationCase.model_validate(curated_from_run_response.json())
            assert curated_from_run.branch_ids == ["default"]
            assert curated_from_run.turns[-1].checks

            events_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{gated_payload.run.run_id}/events"
            )
            assert events_response.status_code == 200, events_response.text
            events = ListResponse[EvaluationRunEvent].model_validate(events_response.json())
            assert EvaluationEventType.GATE_EVALUATED in {item.event_type for item in events.items}
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_suite_api_rejects_missing_flow_and_missing_suite(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        missing_flow = await client.post(
            "/flows/api/v1/evaluation/suites",
            json={
                "flow_id": f"missing_eval_lab_{unique_id}",
                "name": f"Missing flow suite {unique_id}",
            },
        )
        assert missing_flow.status_code == 404, missing_flow.text
        assert "Flow not found" in missing_flow.text

        missing_suite = await client.get(
            f"/flows/api/v1/evaluation/suites/missing-suite-{unique_id}"
        )
        assert missing_suite.status_code == 404, missing_suite.text
        assert "Evaluation suite not found" in missing_suite.text

    async def test_api_rejects_missing_nested_resources(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        missing_suite_id = f"missing-suite-{unique_id}"
        missing_case_id = f"missing-case-{unique_id}"

        update_suite = await client.put(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}",
            json={"name": "missing", "description": "", "tags": []},
        )
        assert update_suite.status_code == 404, update_suite.text

        create_case = await client.post(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/cases",
            json={
                "name": "missing",
                "branch_ids": "*",
                "turns": [{"input": {"type": "text", "content": "x"}}],
            },
        )
        assert create_case.status_code == 404, create_case.text

        list_cases = await client.get(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/cases"
        )
        assert list_cases.status_code == 404, list_cases.text

        update_case = await client.put(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/cases/{missing_case_id}",
            json={
                "name": "missing",
                "branch_ids": "*",
                "turns": [{"input": {"type": "text", "content": "x"}}],
            },
        )
        assert update_case.status_code == 404, update_case.text

        delete_case = await client.delete(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/cases/{missing_case_id}"
        )
        assert delete_case.status_code == 404, delete_case.text

        run = await client.post(
            "/flows/api/v1/evaluation/runs",
            json={
                "suite_id": missing_suite_id,
                "branch_id": "default",
                "scope": {"type": "suite"},
            },
        )
        assert run.status_code == 404, run.text

        get_run = await client.get(f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}")
        assert get_run.status_code == 404, get_run.text

        list_events = await client.get(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/events"
        )
        assert list_events.status_code == 404, list_events.text

        list_case_runs = await client.get(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/cases"
        )
        assert list_case_runs.status_code == 404, list_case_runs.text

        cancel_run = await client.post(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/cancel"
        )
        assert cancel_run.status_code == 404, cancel_run.text

        list_annotations = await client.get(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/annotations"
        )
        assert list_annotations.status_code == 404, list_annotations.text

        create_annotation = await client.post(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/annotations",
            json={"annotation_type": "comment", "comment": "missing"},
        )
        assert create_annotation.status_code == 404, create_annotation.text

        update_annotation = await client.put(
            f"/flows/api/v1/evaluation/annotations/missing-annotation-{unique_id}",
            json={"annotation_type": "comment", "comment": "missing"},
        )
        assert update_annotation.status_code == 404, update_annotation.text

        delete_annotation = await client.delete(
            f"/flows/api/v1/evaluation/annotations/missing-annotation-{unique_id}"
        )
        assert delete_annotation.status_code == 404, delete_annotation.text

        compare = await client.get(
            "/flows/api/v1/evaluation/runs/compare",
            params={
                "left_run_id": f"missing-left-{unique_id}",
                "right_run_id": f"missing-right-{unique_id}",
            },
        )
        assert compare.status_code == 404, compare.text

        list_runs = await client.get(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/runs"
        )
        assert list_runs.status_code == 404, list_runs.text

        archive_suite = await client.post(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/archive"
        )
        assert archive_suite.status_code == 404, archive_suite.text

        archive_rubric = await client.post(
            f"/flows/api/v1/evaluation/rubrics/missing-rubric-{unique_id}/archive"
        )
        assert archive_rubric.status_code == 404, archive_rubric.text

        events_page = await client.get(
            f"/flows/api/v1/evaluation/runs/missing-run-{unique_id}/events-page",
            params={"after_sequence": 0, "limit": 10},
        )
        assert events_page.status_code == 404, events_page.text

        case_run_trace = await client.get(
            f"/flows/api/v1/evaluation/case-runs/missing-case-run-{unique_id}/trace"
        )
        assert case_run_trace.status_code == 404, case_run_trace.text

        matrix = await client.get(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/matrix",
            params={"branch_id": "default"},
        )
        assert matrix.status_code == 404, matrix.text

        baseline_compare = await client.get(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/baseline-compare",
            params={
                "branch_id": "default",
                "run_id": f"missing-run-{unique_id}",
            },
        )
        assert baseline_compare.status_code == 404, baseline_compare.text

        archive_gate_policy = await client.post(
            f"/flows/api/v1/evaluation/gate-policies/missing-gate-{unique_id}/archive"
        )
        assert archive_gate_policy.status_code == 404, archive_gate_policy.text

        create_monitor = await client.post(
            "/flows/api/v1/evaluation/monitors",
            json={
                "suite_id": missing_suite_id,
                "branch_id": "default",
                "name": "missing",
            },
        )
        assert create_monitor.status_code == 404, create_monitor.text

        list_monitors = await client.get(
            f"/flows/api/v1/evaluation/suites/{missing_suite_id}/monitors"
        )
        assert list_monitors.status_code == 404, list_monitors.text

        get_monitor = await client.get(
            f"/flows/api/v1/evaluation/monitors/missing-monitor-{unique_id}"
        )
        assert get_monitor.status_code == 404, get_monitor.text

        update_monitor = await client.put(
            f"/flows/api/v1/evaluation/monitors/missing-monitor-{unique_id}",
            json={
                "branch_id": "default",
                "name": "missing",
                "state": "active",
                "sampling_rate": 1.0,
                "max_traces_per_sample": 10,
            },
        )
        assert update_monitor.status_code == 404, update_monitor.text

        archive_monitor = await client.post(
            f"/flows/api/v1/evaluation/monitors/missing-monitor-{unique_id}/archive"
        )
        assert archive_monitor.status_code == 404, archive_monitor.text

        sample_monitor = await client.post(
            f"/flows/api/v1/evaluation/monitors/missing-monitor-{unique_id}/sample",
            json={"limit": 10},
        )
        assert sample_monitor.status_code == 404, sample_monitor.text

        monitor_observations = await client.get(
            f"/flows/api/v1/evaluation/monitors/missing-monitor-{unique_id}/observations"
        )
        assert monitor_observations.status_code == 404, monitor_observations.text

    async def test_api_error_mapping_covers_generic_validation_error(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _raise_evaluation_error(ValueError("raw evaluation validation"))

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "raw evaluation validation"

    async def test_repository_missing_paths_and_row_parsers(
        self,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        repo = container.evaluation_lab_repository
        missing_id = f"missing-eval-{unique_id}"

        assert await repo.get_suite(missing_id) is None
        assert await repo.get_case(missing_id, missing_id) is None
        assert await repo.delete_case(missing_id, missing_id) is False
        assert await repo.list_suites(missing_id) == []
        assert await repo.list_cases(missing_id) == []
        assert await repo.next_suite_version(missing_id) == 1
        assert await repo.get_suite_version(missing_id) is None
        assert await repo.get_run(missing_id) is None
        assert await repo.list_runs(missing_id, 10) == []
        assert await repo.list_case_runs(missing_id) == []
        assert await repo.get_run_with_cases(missing_id) is None
        assert await repo.next_event_sequence(missing_id) == 1
        assert await repo.list_events(missing_id) == []
        assert await repo.get_annotation(missing_id) is None
        assert await repo.list_annotations(missing_id) == []
        assert await repo.delete_annotation(missing_id) is False

        now = _now()
        suite = EvaluationSuite(
            suite_id=f"suite-{unique_id}",
            flow_id=f"flow-{unique_id}",
            name="Repository parser suite",
            tags=["parser"],
            created_at=now,
            updated_at=now,
        )
        case = _case(
            case_id=f"case-{unique_id}",
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
        )

        created_suite = await repo.create_suite(suite)
        assert created_suite.suite_id == suite.suite_id
        updated_suite = await repo.update_suite(
            suite.model_copy(update={"name": "Repository parser suite updated"})
        )
        assert updated_suite.name == "Repository parser suite updated"
        stored_suite = await repo.get_suite(suite.suite_id)
        assert stored_suite is not None
        assert stored_suite.name == "Repository parser suite updated"

        created_case = await repo.create_case(case)
        assert created_case.case_id == case.case_id
        updated_case = await repo.update_case(
            case.model_copy(update={"enabled": False, "sort_order": 9})
        )
        assert not updated_case.enabled
        stored_case = await repo.get_case(suite.suite_id, case.case_id)
        assert stored_case is not None
        assert stored_case.sort_order == 9

        suite_version = EvaluationSuiteVersion(
            suite_version_id=f"suite-version-direct-{unique_id}",
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            flow_config_version="test-version",
            version=1,
            suite_snapshot=updated_suite,
            cases_snapshot=[updated_case],
            created_at=now,
        )
        created_version = await repo.create_suite_version(suite_version)
        assert created_version.suite_version_id == suite_version.suite_version_id
        assert await repo.next_suite_version(suite.suite_id) == 2
        stored_version = await repo.get_suite_version(suite_version.suite_version_id)
        assert stored_version is not None
        assert stored_version.version == 1

        run = _run(
            run_id=f"run-direct-{unique_id}",
            suite_id=suite.suite_id,
            suite_version_id=suite_version.suite_version_id,
            flow_id=suite.flow_id,
        )
        created_run = await repo.create_run(run)
        assert created_run.run_id == run.run_id
        idempotent_run = await repo.update_run(
            run.model_copy(update={"idempotency_key": f"idempotent-{unique_id}"})
        )
        stored_idempotent_run = await repo.get_run_by_idempotency_key(
            suite_id=suite.suite_id,
            branch_id="default",
            idempotency_key=f"idempotent-{unique_id}",
        )
        assert stored_idempotent_run is not None
        assert stored_idempotent_run.run_id == idempotent_run.run_id
        run_job = EvaluationRunJob(
            run_job_id=f"run-job-direct-{unique_id}",
            run_id=run.run_id,
            taskiq_task_id=f"taskiq-direct-{unique_id}",
            state=EvaluationRunJobState.PENDING,
            context_data={"channel": "repository"},
            trace_context={"trace_id": f"trace-direct-{unique_id}"},
            created_at=now,
            updated_at=now,
        )
        created_run_job = await repo.create_run_job(run_job)
        assert created_run_job.run_job_id == run_job.run_job_id
        stored_run_job = await repo.get_run_job_by_run_id(run.run_id)
        assert stored_run_job is not None
        assert stored_run_job.taskiq_task_id == run_job.taskiq_task_id
        pending_run_jobs = await repo.list_pending_run_jobs(10)
        assert run.run_id in {item.run_id for item in pending_run_jobs}
        updated_run_job = await repo.update_run_job(
            run_job.model_copy(
                update={
                    "state": EvaluationRunJobState.ENQUEUED,
                    "enqueued_at": now,
                    "updated_at": now,
                }
            )
        )
        assert updated_run_job.state == EvaluationRunJobState.ENQUEUED
        with pytest.raises(EvaluationLabValidationError):
            await container.evaluation_lab_service.execute_run_from_taskiq(
                run.run_id,
                EvaluationTaskiqExecutionContext(
                    task_name=TASK_EXECUTE_EVALUATION_RUN,
                    task_id="wrong-taskiq-id",
                    evaluation_run_id=run.run_id,
                ),
            )
        updated_run = await repo.update_run(
            run.model_copy(
                update={
                    "state": EvaluationRunState.PASSED,
                    "passed_case_runs": 1,
                    "average_score": 10.0,
                    "started_at": now,
                    "finished_at": now,
                }
            )
        )
        assert updated_run.state == EvaluationRunState.PASSED
        assert await repo.get_run(run.run_id) is not None
        assert [item.run_id for item in await repo.list_runs(suite.suite_id, 5)] == [
            run.run_id
        ]

        case_run = _case_run(
            case_run_id=f"case-run-direct-{unique_id}",
            run_id=run.run_id,
            case_id=case.case_id,
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
        )
        created_case_run = await repo.create_case_run(case_run)
        assert created_case_run.case_run_id == case_run.case_run_id
        updated_case_run = await repo.update_case_run(
            case_run.model_copy(update={"state": EvaluationCaseRunState.FAILED, "error": "nope"})
        )
        assert updated_case_run.state == EvaluationCaseRunState.FAILED
        assert [item.case_run_id for item in await repo.list_case_runs(run.run_id)] == [
            case_run.case_run_id
        ]
        stored_run_with_cases = await repo.get_run_with_cases(run.run_id)
        assert stored_run_with_cases is not None
        assert stored_run_with_cases.case_runs[0].case_run_id == case_run.case_run_id

        event_model = EvaluationRunEvent(
            event_id=f"event-direct-{unique_id}",
            run_id=run.run_id,
            case_run_id=case_run.case_run_id,
            sequence=1,
            event_type=EvaluationEventType.RUN_CREATED,
            payload={"suite_id": suite.suite_id},
            created_at=now,
        )
        appended_event = await repo.append_event(event_model)
        assert appended_event.event_id == event_model.event_id
        assert await repo.next_event_sequence(run.run_id) == 2
        assert [item.event_id for item in await repo.list_events(run.run_id)] == [
            event_model.event_id
        ]
        events_page = await repo.list_events_after_sequence(
            run.run_id,
            after_sequence=0,
            limit=1,
        )
        assert [item.event_id for item in events_page] == [event_model.event_id]
        assert await repo.list_events_after_sequence(
            run.run_id,
            after_sequence=1,
            limit=1,
        ) == []

        annotation_model = EvaluationAnnotation(
            annotation_id=f"annotation-direct-{unique_id}",
            run_id=run.run_id,
            case_run_id=case_run.case_run_id,
            case_id=case.case_id,
            annotation_type=EvaluationAnnotationType.COMMENT,
            comment="repository annotation",
            payload={"flag": True},
            created_by="reviewer",
            created_at=now,
            updated_at=now,
        )
        created_annotation = await repo.create_annotation(annotation_model)
        assert created_annotation.annotation_id == annotation_model.annotation_id
        stored_annotation = await repo.get_annotation(annotation_model.annotation_id)
        assert stored_annotation is not None
        assert stored_annotation.payload == {"flag": True}
        updated_annotation = await repo.update_annotation(
            annotation_model.model_copy(
                update={
                    "annotation_type": EvaluationAnnotationType.ISSUE,
                    "comment": "updated",
                    "payload": {"flag": False},
                }
            )
        )
        assert updated_annotation.annotation_type == EvaluationAnnotationType.ISSUE
        assert [item.annotation_id for item in await repo.list_annotations(run.run_id)] == [
            annotation_model.annotation_id
        ]
        assert await repo.delete_annotation(annotation_model.annotation_id)
        assert await repo.get_annotation(annotation_model.annotation_id) is None
        assert not await repo.delete_annotation(annotation_model.annotation_id)

        monitor_model = EvaluationMonitor(
            monitor_id=f"monitor-direct-{unique_id}",
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            branch_id="default",
            name="Repository monitor",
            state=EvaluationMonitorState.ACTIVE,
            sampling_rate=1.0,
            max_traces_per_sample=10,
            filter=EvaluationMonitorFilter(),
            created_by="repository",
            created_at=now,
            updated_at=now,
        )
        created_monitor = await repo.create_monitor(monitor_model)
        assert created_monitor.monitor_id == monitor_model.monitor_id
        updated_monitor = await repo.update_monitor(
            monitor_model.model_copy(
                update={
                    "state": EvaluationMonitorState.PAUSED,
                    "updated_at": now,
                }
            )
        )
        assert updated_monitor.state == EvaluationMonitorState.PAUSED
        stored_monitor = await repo.get_monitor(monitor_model.monitor_id)
        assert stored_monitor is not None
        assert stored_monitor.monitor_id == monitor_model.monitor_id
        assert [item.monitor_id for item in await repo.list_monitors(suite.suite_id)] == [
            monitor_model.monitor_id
        ]
        observation_model = EvaluationMonitorObservation(
            observation_id=f"observation-direct-{unique_id}",
            monitor_id=monitor_model.monitor_id,
            suite_id=suite.suite_id,
            flow_id=suite.flow_id,
            branch_id="default",
            trace_id=f"trace-observation-{unique_id}",
            task_id=f"task-observation-{unique_id}",
            session_id=f"session-observation-{unique_id}",
            state=EvaluationMonitorObservationState.SAMPLED,
            span_count=1,
            payload={"spans": [], "filter": {}},
            sampled_at=now,
        )
        created_observation = await repo.upsert_monitor_observation(observation_model)
        assert created_observation.observation_id == observation_model.observation_id
        stored_observation = await repo.get_monitor_observation(
            monitor_model.monitor_id,
            observation_model.trace_id,
        )
        assert stored_observation is not None
        assert stored_observation.trace_id == observation_model.trace_id
        assert [
            item.observation_id
            for item in await repo.list_monitor_observations(monitor_model.monitor_id, 10)
        ] == [observation_model.observation_id]

        version_row: dict[str, EvaluationLabRowValue] = {
            "suite_version_id": f"version-{unique_id}",
            "suite_id": suite.suite_id,
            "flow_id": suite.flow_id,
            "flow_config_version": "test-version",
            "version": 3,
            "suite_snapshot": json.dumps(suite.model_dump(mode="json")),
            "cases_snapshot": json.dumps([case.model_dump(mode="json")]),
            "created_at": now,
        }
        parsed_version = repo._suite_version_from_row(version_row)
        assert parsed_version.version == 3
        assert parsed_version.cases_snapshot[0].case_id == case.case_id

        version_row_python = dict(version_row)
        version_row_python["suite_snapshot"] = suite.model_dump(mode="json")
        version_row_python["cases_snapshot"] = [case.model_dump(mode="json")]
        parsed_version_python = repo._suite_version_from_row(version_row_python)
        assert parsed_version_python.suite_snapshot.suite_id == suite.suite_id

        case_run_row = {
            "case_run_id": f"case-run-{unique_id}",
            "run_id": f"run-{unique_id}",
            "case_id": case.case_id,
            "trial_index": 1,
            "suite_id": suite.suite_id,
            "flow_id": suite.flow_id,
            "branch_id": "default",
            "state": str(EvaluationCaseRunState.PASSED),
            "task_id": "task-parser",
            "context_id": "ctx-parser",
            "session_id": f"{suite.flow_id}:ctx-parser",
            "trace_id": "trace-parser",
            "duration_ms": 25,
            "input_tokens": 2,
            "output_tokens": 3,
            "total_tokens": 5,
            "billing_quantity": 5,
            "turns_count": 1,
            "scores": json.dumps({"quality": 7.5, "gate": True}),
            "total_score": 8.75,
            "judge_feedback": "ok",
            "dialog": json.dumps([{"role": "user", "content": "hello"}]),
            "error": None,
            "started_at": now,
            "finished_at": now,
            "created_at": now,
            "updated_at": now,
        }
        parsed_case_run = repo._case_run_from_row(case_run_row)
        assert parsed_case_run.trial_index == 1
        assert parsed_case_run.total_tokens == 5
        assert parsed_case_run.scores == {"quality": 7.5, "gate": True}
        assert parsed_case_run.dialog[0].content == "hello"

        case_run_row_none = dict(case_run_row)
        case_run_row_none["scores"] = None
        case_run_row_none["dialog"] = None
        case_run_row_none["task_id"] = None
        case_run_row_none["context_id"] = None
        case_run_row_none["session_id"] = None
        case_run_row_none["trace_id"] = None
        case_run_row_none["duration_ms"] = None
        case_run_row_none["total_score"] = None
        case_run_row_none["judge_feedback"] = None
        case_run_row_none["started_at"] = None
        case_run_row_none["finished_at"] = None
        parsed_empty_case_run = repo._case_run_from_row(case_run_row_none)
        assert parsed_empty_case_run.dialog == []
        assert parsed_empty_case_run.scores is None

        event = repo._event_from_row(
            {
                "event_id": f"event-{unique_id}",
                "run_id": f"run-{unique_id}",
                "case_run_id": None,
                "sequence": 1,
                "event_type": str(EvaluationEventType.RUN_CREATED),
                "payload": json.dumps({"suite_id": suite.suite_id}),
                "created_at": now,
            }
        )
        assert event.payload == {"suite_id": suite.suite_id}

        parsed_annotation = repo._annotation_from_row(
            {
                "annotation_id": f"annotation-{unique_id}",
                "run_id": run.run_id,
                "case_run_id": None,
                "case_id": None,
                "annotation_type": str(EvaluationAnnotationType.COMMENT),
                "comment": "parsed",
                "payload": json.dumps({"parsed": True}),
                "created_by": "reviewer",
                "created_at": now,
                "updated_at": now,
            }
        )
        assert parsed_annotation.payload == {"parsed": True}

        assert repo._json_list_strings('["alpha"]', "tags") == ["alpha"]
        assert repo._optional_string({"value": None}, "value") is None
        assert repo._optional_int({"value": None}, "value") is None
        assert repo._optional_float({"value": None}, "value") is None
        assert repo._optional_datetime({"value": None}, "value") is None

        invalid_rows = [
            (repo._string, {"value": 1}, "value"),
            (repo._optional_string, {"value": 1}, "value"),
            (repo._int, {"value": True}, "value"),
            (repo._optional_int, {"value": True}, "value"),
            (repo._optional_float, {"value": True}, "value"),
            (repo._datetime, {"value": "bad"}, "value"),
            (repo._optional_datetime, {"value": "bad"}, "value"),
        ]
        for parser, row, key in invalid_rows:
            with pytest.raises(ValueError):
                parser(row, key)

        with pytest.raises(ValueError):
            repo._json_list_strings([{"not": "a string"}], "tags")
        with pytest.raises(ValueError):
            _int_scalar(True, "bad_int")

    async def test_service_deterministic_helpers_and_strict_errors(
        self,
        container: FlowContainer,
    ) -> None:
        service: EvaluationLabService = container.evaluation_lab_service
        state_json: JsonObject = {
            "answer": "42",
            "metrics": {"score": 7, "items": ["alpha", "beta"]},
            "flag": True,
        }

        assert service._source_text(
            EvaluationCheckSource.STATE,
            None,
            state_json,
            "response",
        ) == json.dumps(state_json, ensure_ascii=False, sort_keys=True)
        assert service._source_value(
            EvaluationCheckSource.STATE,
            "metrics.items.1",
            state_json,
            "response",
        ) == "beta"
        with pytest.raises(EvaluationLabValidationError):
            service._source_value(
                EvaluationCheckSource.RESPONSE,
                "answer",
                state_json,
                "response",
            )

        assert service._normalize_strings(["Alpha"], case_sensitive=False) == ["alpha"]
        assert service._normalize_strings(["Alpha"], case_sensitive=True) == ["Alpha"]

        contains_any = service._check_contains(
            EvaluationCheckContains(
                type="contains",
                values=["missing", "Echo"],
                mode=EvaluationContainsMode.ANY,
            ),
            state_json,
            "Echo response",
        )
        assert contains_any.passed

        not_contains = service._check_not_contains(
            EvaluationCheckNotContains(
                type="not_contains",
                values=["fatal"],
                case_sensitive=True,
            ),
            state_json,
            "FATAL is only upper-case",
        )
        assert not_contains.passed

        regex = service._check_regex(
            EvaluationCheckRegex(type="regex", pattern="^Echo", ignore_case=False),
            state_json,
            "Echo response",
        )
        assert regex.passed

        length = service._check_length(
            EvaluationCheckLength(type="length", max_chars=4),
            state_json,
            "1234",
        )
        assert length.passed

        exists = service._check_state_path(
            EvaluationCheckStatePath(
                type="state_path",
                path="metrics.items.0",
                operator=EvaluationStateOperator.EXISTS,
            ),
            state_json,
        )
        assert exists.passed

        assert not service._path_exists(state_json, "metrics.items.99")
        with pytest.raises(EvaluationLabValidationError):
            service._read_path(state_json, "missing")
        with pytest.raises(EvaluationLabValidationError):
            service._read_path(state_json, "metrics.items.bad")
        with pytest.raises(EvaluationLabValidationError):
            service._read_path(state_json, "metrics.items.9")
        with pytest.raises(EvaluationLabValidationError):
            service._read_path(state_json, "answer.value")

        invalid_schema = service._check_json_schema(
            EvaluationCheckJsonSchema(
                type="json_schema",
                source=EvaluationCheckSource.STATE,
                state_path="metrics",
                json_schema={"type": "object", "required": ["missing"]},
            ),
            state_json,
            "response",
        )
        assert not invalid_schema.passed

        assert service._compare_state_values("42", "42", EvaluationStateOperator.EQ)
        assert service._compare_state_values("42", "41", EvaluationStateOperator.NE)
        assert not service._compare_state_values(True, 1, EvaluationStateOperator.GT)
        assert not service._compare_state_values(1, True, EvaluationStateOperator.GT)
        assert service._compare_state_values(2, 1, EvaluationStateOperator.GT)
        assert service._compare_state_values(2, 2, EvaluationStateOperator.GTE)
        assert service._compare_state_values(1, 2, EvaluationStateOperator.LT)
        assert service._compare_state_values(2, 2, EvaluationStateOperator.LTE)
        assert service._compare_state_values("b", "a", EvaluationStateOperator.GT)
        assert service._compare_state_values("b", "b", EvaluationStateOperator.GTE)
        assert service._compare_state_values("a", "b", EvaluationStateOperator.LT)
        assert service._compare_state_values("a", "a", EvaluationStateOperator.LTE)
        assert not service._compare_state_values(1, "1", EvaluationStateOperator.GT)
        with pytest.raises(EvaluationLabValidationError):
            service._compare_numbers(1.0, 1.0, EvaluationStateOperator.EQ)
        with pytest.raises(EvaluationLabValidationError):
            service._compare_strings("a", "a", EvaluationStateOperator.EQ)

        assert service._normalize_scores(True) == {"result": True}
        assert service._normalize_scores(7) == {"result": 7.0}
        assert service._normalize_scores({"quality": 8, "gate": False}) == {
            "quality": 8.0,
            "gate": False,
        }
        with pytest.raises(EvaluationLabValidationError):
            service._normalize_scores({})
        with pytest.raises(EvaluationLabValidationError):
            service._normalize_scores({"bad": "score"})
        with pytest.raises(EvaluationLabValidationError):
            service._normalize_scores(["bad"])

        assert not service._scores_passed({"gate": False})
        assert not service._scores_passed({"quality": 4.9})
        assert service._scores_passed({"quality": 5.0, "gate": True})
        assert service._total_score(None) is None
        assert service._total_score({}) is None

        left = _case_run(
            case_run_id="left",
            run_id="run-left",
            case_id="case",
            suite_id="suite",
            flow_id="flow",
            total_score=None,
            duration_ms=None,
        )
        right = _case_run(
            case_run_id="right",
            run_id="run-right",
            case_id="case",
            suite_id="suite",
            flow_id="flow",
        )
        assert service._score_delta(None, right) is None
        assert service._score_delta(left, right) is None
        assert service._duration_delta(None, right) is None
        assert service._duration_delta(left, right) is None
        assert service._elapsed_ms()() >= 0

        assert _llm_usage_tokens({}) == (None, None)
        assert _llm_usage_tokens({"usage": {"input_tokens": 3}}) == (3, None)
        assert _llm_usage_tokens({"usage": {"output_tokens": 5}}) == (None, 5)
        with pytest.raises(EvaluationLabValidationError):
            _llm_usage_tokens({"usage": {"input_tokens": True}})
        with pytest.raises(EvaluationLabValidationError):
            _llm_usage_tokens({"usage": {"output_tokens": "5"}})

    async def test_service_trace_node_resolution_and_case_selection(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_helpers_{unique_id}"
        await _create_code_flow(client, flow_id)
        service: EvaluationLabService = container.evaluation_lab_service
        try:
            flow = await container.flow_repository.get(flow_id)
            assert flow is not None
            state = _state(flow_id, unique_id, flow.version)
            await service._start_evaluation_workflow(
                state,
                flow_id=flow_id,
                branch_id="default",
            )
            await service._start_evaluation_workflow(
                state,
                flow_id=flow_id,
                branch_id="default",
            )
            with pytest.raises(RuntimeError):
                await service._start_evaluation_workflow(
                    _state("other_flow", unique_id),
                    flow_id=flow_id,
                    branch_id="default",
                )

            runtime = container.workflow_runtime
            _ = await runtime.record_state_event(
                state.session_id,
                state,
                event_type=WorkflowEventType.node_failed,
                payload=NodeFailedPayload(
                    error="boom",
                    recover_sequence=0,
                    current_nodes=["failed_node"],
                    failed_nodes=["failed_node"],
                ),
            )
            _ = await runtime.record_state_event(
                state.session_id,
                state,
                event_type=WorkflowEventType.activity_started,
                payload=ActivityLifecyclePayload(
                    activity_id="activity-1",
                    activity_attempt_id="activity-1-attempt-1",
                    activity_type="tool",
                    activity_status=ActivityStatus.started,
                    node_id="tool_node",
                    tool_call_id="tool_call_1",
                    input_hash="hash",
                    side_effect_policy=SideEffectPolicy.non_idempotent,
                    attempt=1,
                ),
            )

            failed_trace = await service._check_trace_assertion(
                EvaluationCheckTraceAssertion(
                    type="trace_assertion",
                    assertion=EvaluationTraceAssertion.NODE_FAILED,
                    value="failed_node",
                ),
                state,
            )
            assert failed_trace.passed

            tool_node_trace = await service._check_trace_assertion(
                EvaluationCheckTraceAssertion(
                    type="trace_assertion",
                    assertion=EvaluationTraceAssertion.TOOL_CALLED,
                    value="tool_node",
                ),
                state,
            )
            assert tool_node_trace.passed

            tool_call_trace = await service._check_trace_assertion(
                EvaluationCheckTraceAssertion(
                    type="trace_assertion",
                    assertion=EvaluationTraceAssertion.TOOL_CALLED,
                    value="tool_call_1",
                ),
                state,
            )
            assert tool_call_trace.passed

            missing_trace = await service._check_trace_assertion(
                EvaluationCheckTraceAssertion(
                    type="trace_assertion",
                    assertion=EvaluationTraceAssertion.NODE_FAILED,
                    value="missing_node",
                ),
                state,
            )
            assert not missing_trace.passed

            inline_input_node = await service._resolve_input_node(
                EvaluationInputNode(
                    type="node",
                    node={
                        "node_id": "inline_input",
                        "type": NodeType.LLM_NODE.value,
                        "prompt": "Inline input prompt",
                    },
                ),
                state,
            )
            assert inline_input_node.prompt == "Inline input prompt"

            flow_input_node = await service._resolve_input_node(
                EvaluationInputNode(type="node", node_id="echo"),
                state,
            )
            assert flow_input_node.node_id == "echo"

            stored_node = NodeConfig(
                node_id=f"stored_judge_{unique_id}",
                type=NodeType.LLM_NODE,
                prompt="Stored judge prompt",
            )
            _ = await container.node_repository.set(stored_node)
            try:
                stored_input_node = await service._resolve_input_node(
                    EvaluationInputNode(type="node", node_id=stored_node.node_id),
                    state,
                )
                assert stored_input_node.prompt == "Stored judge prompt"

                assert await service._judge_prompt(
                    EvaluationCheckLlmJudge(
                        type="llm_judge",
                        rubric_version_id="rubric-version",
                        judge_node={
                            "node_id": "inline_judge",
                            "type": NodeType.LLM_NODE.value,
                            "prompt": "Inline judge prompt",
                        },
                    ),
                    state,
                ) == "Inline judge prompt"
                assert await service._judge_prompt(
                    EvaluationCheckLlmJudge(
                        type="llm_judge",
                        rubric_version_id="rubric-version",
                        judge_node_id=stored_node.node_id,
                    ),
                    state,
                ) == "Stored judge prompt"
                assert await service._judge_prompt(
                    EvaluationCheckLlmJudge(
                        type="llm_judge",
                        rubric_version_id="rubric-version",
                    ),
                    state,
                ) == "You are a strict evaluator. Score the assistant response against the rubric."
            finally:
                _ = await container.node_repository.delete(stored_node.node_id)

            with pytest.raises(EvaluationLabValidationError):
                await service._resolve_input_node(EvaluationInputNode(type="node"), state)
            with pytest.raises(EvaluationLabNotFoundError):
                await service._resolve_input_node(
                    EvaluationInputNode(type="node", node_id=f"missing-node-{unique_id}"),
                    state,
                )

            missing_flow_case = _case(
                case_id=f"case-missing-flow-{unique_id}",
                suite_id=f"suite-{unique_id}",
                flow_id=flow_id,
            ).model_copy(
                update={
                    "target": EvaluationTargetFlow(
                        type="flow",
                        flow_id=f"missing-target-flow-{unique_id}",
                    )
                }
            )
            with pytest.raises(EvaluationLabNotFoundError):
                await service._create_target_runtime(missing_flow_case, "default", flow.version)

            suite = await _create_suite(client, flow_id, f"Selection suite {unique_id}")
            other_branch_case_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"Other branch {unique_id}",
                    "branch_ids": ["other"],
                    "turns": [{"input": {"type": "text", "content": "ping"}}],
                },
            )
            assert other_branch_case_response.status_code == 200, other_branch_case_response.text
            other_branch_case = EvaluationCase.model_validate(
                other_branch_case_response.json()
            )

            with pytest.raises(EvaluationLabNotFoundError):
                await service._select_cases(
                    suite_id=suite.suite_id,
                    branch_id="default",
                    scope=EvaluationRunCasesScope(
                        type="cases",
                        case_ids=[other_branch_case.case_id],
                    ),
                )
            assert not service._case_matches_branch(other_branch_case, "default")
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_executes_flow_records_events_and_compare(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_run_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Run suite {unique_id}")
            suite_id = suite.suite_id
            case = await _create_passing_case(client, suite_id, f"Passing case {unique_id}")

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite_id,
                    "branch_id": "default",
                    "scope": {"type": "suite"},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())
            assert created_run.run.taskiq_task_id is not None
            run_payload = await _wait_for_run(client, created_run.run.run_id)
            assert run_payload.run.state == EvaluationRunState.PASSED, (
                run_payload.run.error_message
            )
            assert run_payload.run.passed_case_runs == 1
            assert run_payload.run.flow_config_version
            assert run_payload.case_runs[0].state == EvaluationCaseRunState.PASSED
            assert run_payload.case_runs[0].total_score == 10.0
            assert "Echo: ping 42" in run_payload.case_runs[0].dialog[1].content

            run_id = run_payload.run.run_id
            stored = await container.evaluation_lab_repository.get_run_with_cases(run_id)
            assert stored is not None
            assert stored.run.suite_id == suite_id
            assert stored.case_runs[0].case_id == case.case_id

            events_response = await client.get(f"/flows/api/v1/evaluation/runs/{run_id}/events")
            assert events_response.status_code == 200, events_response.text
            events = ListResponse[EvaluationRunEvent].model_validate(events_response.json())
            event_types = [item.event_type for item in events.items]
            assert "run_created" in event_types
            assert "message_recorded" in event_types
            assert "score_recorded" in event_types
            assert "case_finished" in event_types

            case_runs_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{run_id}/cases"
            )
            assert case_runs_response.status_code == 200, case_runs_response.text
            case_runs = ListResponse[EvaluationCaseRun].model_validate(
                case_runs_response.json()
            )
            assert [item.case_id for item in case_runs.items] == [case.case_id]

            annotation_response = await client.post(
                f"/flows/api/v1/evaluation/runs/{run_id}/annotations",
                json={
                    "case_run_id": run_payload.case_runs[0].case_run_id,
                    "annotation_type": "approval",
                    "comment": "approved by reviewer",
                    "payload": {"severity": "none"},
                },
            )
            assert annotation_response.status_code == 200, annotation_response.text
            annotation = EvaluationAnnotation.model_validate(annotation_response.json())
            assert annotation.case_id == case.case_id
            assert annotation.annotation_type == EvaluationAnnotationType.APPROVAL

            annotations_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{run_id}/annotations"
            )
            assert annotations_response.status_code == 200, annotations_response.text
            annotations = ListResponse[EvaluationAnnotation].model_validate(
                annotations_response.json()
            )
            assert [item.annotation_id for item in annotations.items] == [
                annotation.annotation_id
            ]

            updated_annotation_response = await client.put(
                f"/flows/api/v1/evaluation/annotations/{annotation.annotation_id}",
                json={
                    "annotation_type": "issue",
                    "comment": "needs follow-up",
                    "payload": {"severity": "low"},
                },
            )
            assert updated_annotation_response.status_code == 200
            updated_annotation = EvaluationAnnotation.model_validate(
                updated_annotation_response.json()
            )
            assert updated_annotation.annotation_type == EvaluationAnnotationType.ISSUE

            deleted_annotation_response = await client.delete(
                f"/flows/api/v1/evaluation/annotations/{annotation.annotation_id}"
            )
            assert deleted_annotation_response.status_code == 200
            assert deleted_annotation_response.json() == {"deleted": True}

            second_run = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert second_run.status_code == 200, second_run.text
            created_second_run = EvaluationRunWithCases.model_validate(second_run.json())
            second_run_payload = await _wait_for_run(
                client,
                created_second_run.run.run_id,
            )

            compare = await client.get(
                "/flows/api/v1/evaluation/runs/compare",
                params={
                    "left_run_id": run_id,
                    "right_run_id": second_run_payload.run.run_id,
                },
            )
            assert compare.status_code == 200, compare.text
            comparison = EvaluationRunComparison.model_validate(compare.json())
            assert comparison.cases[0].case_id == case.case_id
            assert comparison.cases[0].score_delta == 0.0

            suite_runs_response = await client.get(
                f"/flows/api/v1/evaluation/suites/{suite_id}/runs"
            )
            assert suite_runs_response.status_code == 200, suite_runs_response.text
            suite_runs = ListResponse[EvaluationRun].model_validate(suite_runs_response.json())
            assert len(suite_runs.items) >= 2
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_final_gap_api_covers_idempotency_matrix_events_trace_baseline_and_archive(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_final_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Final suite {unique_id}")
            case = await _create_passing_case(client, suite.suite_id, f"Final case {unique_id}")
            rubric = await _create_rubric(client, flow_id, f"Final rubric {unique_id}")
            gate_policy_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/gate-policies",
                json={
                    "branch_id": "default",
                    "name": f"Final gate {unique_id}",
                    "min_pass_rate": 1.0,
                    "max_failed_case_runs": 0,
                    "max_error_case_runs": 0,
                },
            )
            assert gate_policy_response.status_code == 200, gate_policy_response.text
            gate_policy = EvaluationGatePolicy.model_validate(gate_policy_response.json())

            idempotency_key = f"run-key-{unique_id}"
            first_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                    "idempotency_key": idempotency_key,
                },
            )
            assert first_run_response.status_code == 200, first_run_response.text
            first_created = EvaluationRunWithCases.model_validate(first_run_response.json())
            first_payload = await _wait_for_run(client, first_created.run.run_id)
            assert first_payload.run.state == EvaluationRunState.PASSED
            assert first_payload.run.idempotency_key == idempotency_key

            duplicate_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                    "idempotency_key": idempotency_key,
                },
            )
            assert duplicate_run_response.status_code == 200, duplicate_run_response.text
            duplicate_payload = EvaluationRunWithCases.model_validate(
                duplicate_run_response.json()
            )
            assert duplicate_payload.run.run_id == first_payload.run.run_id

            events_page_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{first_payload.run.run_id}/events-page",
                params={"after_sequence": 0, "limit": 2},
            )
            assert events_page_response.status_code == 200, events_page_response.text
            events_page = EvaluationRunEventsPage.model_validate(events_page_response.json())
            assert len(events_page.items) == 2
            assert events_page.has_more
            assert events_page.next_sequence == events_page.items[-1].sequence

            next_events_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{first_payload.run.run_id}/events-page",
                params={"after_sequence": events_page.next_sequence, "limit": 100},
            )
            assert next_events_response.status_code == 200, next_events_response.text
            next_events_page = EvaluationRunEventsPage.model_validate(next_events_response.json())
            assert next_events_page.items
            assert not next_events_page.has_more

            matrix_response = await client.get(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/matrix",
                params={"branch_id": "default", "limit": 10},
            )
            assert matrix_response.status_code == 200, matrix_response.text
            matrix = EvaluationResultsMatrix.model_validate(matrix_response.json())
            assert [item.case_id for item in matrix.cases] == [case.case_id]
            assert first_payload.run.run_id in {item.run_id for item in matrix.runs}
            assert first_payload.case_runs[0].case_run_id in {
                item.case_run_id for item in matrix.cells
            }

            trace_response = await client.get(
                f"/flows/api/v1/evaluation/case-runs/{first_payload.case_runs[0].case_run_id}/trace"
            )
            assert trace_response.status_code == 200, trace_response.text
            trace = EvaluationCaseRunTrace.model_validate(trace_response.json())
            assert trace.case_run.case_run_id == first_payload.case_runs[0].case_run_id
            assert trace.workflow_events
            assert any(item.node_id == "echo" for item in trace.node_steps)

            baseline_response = await client.put(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/baselines/default",
                json={"run_id": first_payload.run.run_id},
            )
            assert baseline_response.status_code == 200, baseline_response.text

            second_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert second_run_response.status_code == 200, second_run_response.text
            second_created = EvaluationRunWithCases.model_validate(second_run_response.json())
            second_payload = await _wait_for_run(client, second_created.run.run_id)

            baseline_compare_response = await client.get(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/baseline-compare",
                params={
                    "branch_id": "default",
                    "run_id": second_payload.run.run_id,
                },
            )
            assert baseline_compare_response.status_code == 200, baseline_compare_response.text
            baseline_compare = EvaluationBaselineComparison.model_validate(
                baseline_compare_response.json()
            )
            assert baseline_compare.baseline.run_id == first_payload.run.run_id
            assert baseline_compare.comparison.left_run.run_id == first_payload.run.run_id
            assert baseline_compare.comparison.right_run.run_id == second_payload.run.run_id

            archived_rubric_response = await client.post(
                f"/flows/api/v1/evaluation/rubrics/{rubric.rubric.rubric_id}/archive"
            )
            assert archived_rubric_response.status_code == 200, archived_rubric_response.text
            archived_rubric = EvaluationRubric.model_validate(archived_rubric_response.json())
            assert archived_rubric.archived_at is not None

            archived_gate_response = await client.post(
                f"/flows/api/v1/evaluation/gate-policies/{gate_policy.gate_policy_id}/archive"
            )
            assert archived_gate_response.status_code == 200, archived_gate_response.text
            archived_gate = EvaluationGatePolicy.model_validate(archived_gate_response.json())
            assert archived_gate.archived_at is not None

            archived_suite_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/archive"
            )
            assert archived_suite_response.status_code == 200, archived_suite_response.text
            archived_suite = EvaluationSuite.model_validate(archived_suite_response.json())
            assert archived_suite.archived_at is not None
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_pending_run_jobs_are_durable_and_taskiq_gated(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_jobs_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Job suite {unique_id}")
            case = await _create_passing_case(client, suite.suite_id, f"Job case {unique_id}")
            created = await container.evaluation_lab_service.create_run(
                EvaluationRunCreateRequest(
                    suite_id=suite.suite_id,
                    branch_id="default",
                    scope=EvaluationRunCasesScope(type="cases", case_ids=[case.case_id]),
                )
            )
            context = get_context()
            assert context is not None
            job = await container.evaluation_lab_service.create_run_job(
                created.run.run_id,
                context_data=context.to_dict(),
                trace_context=None,
            )
            assert job.state == EvaluationRunJobState.PENDING

            with pytest.raises(EvaluationLabValidationError):
                await container.evaluation_lab_service.execute_run_from_taskiq(
                    created.run.run_id,
                    EvaluationTaskiqExecutionContext(
                        task_name=TASK_EXECUTE_EVALUATION_RUN,
                        task_id=job.taskiq_task_id,
                        evaluation_run_id=created.run.run_id,
                    ),
                )

            enqueue_response = await client.post(
                "/flows/api/v1/evaluation/run-jobs/enqueue-pending",
                params={"limit": 10},
            )
            assert enqueue_response.status_code == 200, enqueue_response.text
            enqueue_result = EvaluationPendingRunJobsEnqueueResult.model_validate(
                enqueue_response.json()
            )
            assert created.run.run_id in enqueue_result.enqueued_run_ids
            assert created.run.run_id not in enqueue_result.failed_run_ids

            stored_job = await container.evaluation_lab_service.get_run_job(created.run.run_id)
            assert stored_job.state == EvaluationRunJobState.ENQUEUED
            run_payload = await _wait_for_run(client, created.run.run_id)
            assert run_payload.run.state == EvaluationRunState.PASSED
            assert run_payload.case_runs[0].state == EvaluationCaseRunState.PASSED
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_worker_task_contracts_use_real_taskiq_contexts(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_worker_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Worker suite {unique_id}")
            case = await _create_passing_case(client, suite.suite_id, f"Worker case {unique_id}")
            context = get_context()
            assert context is not None

            invalid_context = _taskiq_context(
                task_name=TASK_EXECUTE_EVALUATION_RUN,
                task_id=f"invalid-taskiq-{unique_id}",
                labels={"evaluation_run_id": f"missing-run-{unique_id}"},
            )
            with pytest.raises(ValueError, match="Context is required"):
                await execute_evaluation_run.original_func(
                    f"missing-run-{unique_id}",
                    invalid_context,
                    context_data=None,
                )
            with pytest.raises(ValueError, match="TaskIQ label evaluation_run_id is required"):
                await execute_evaluation_run.original_func(
                    f"missing-run-{unique_id}",
                    _taskiq_context(
                        task_name=TASK_EXECUTE_EVALUATION_RUN,
                        task_id=f"missing-label-taskiq-{unique_id}",
                        labels={},
                    ),
                    context_data=context.to_dict(),
                )
            with pytest.raises(
                ValueError,
                match="TaskIQ label evaluation_run_id must be a non-empty string",
            ):
                await execute_evaluation_run.original_func(
                    f"missing-run-{unique_id}",
                    _taskiq_context(
                        task_name=TASK_EXECUTE_EVALUATION_RUN,
                        task_id=f"bad-label-taskiq-{unique_id}",
                        labels={"evaluation_run_id": ""},
                    ),
                    context_data=context.to_dict(),
                )
            with pytest.raises(ValueError, match="Context is required"):
                await enqueue_pending_evaluation_runs.original_func(
                    _taskiq_context(
                        task_name=TASK_ENQUEUE_PENDING_EVALUATION_RUNS,
                        task_id=f"enqueue-no-context-{unique_id}",
                        labels={},
                    ),
                    context_data=None,
                )
            with pytest.raises(ValueError, match="limit must be >= 1"):
                await enqueue_pending_evaluation_runs.original_func(
                    _taskiq_context(
                        task_name=TASK_ENQUEUE_PENDING_EVALUATION_RUNS,
                        task_id=f"enqueue-invalid-{unique_id}",
                        labels={},
                    ),
                    context_data=context.to_dict(),
                    limit=0,
                )

            created = await container.evaluation_lab_service.create_run(
                EvaluationRunCreateRequest(
                    suite_id=suite.suite_id,
                    branch_id="default",
                    scope=EvaluationRunCasesScope(type="cases", case_ids=[case.case_id]),
                )
            )
            job = await container.evaluation_lab_service.create_run_job(
                created.run.run_id,
                context_data=context.to_dict(),
                trace_context={
                    "trace_id": f"workertrace{unique_id}",
                    "span_id": f"workerspan{unique_id}",
                },
            )
            _ = await container.evaluation_lab_service.mark_run_job_enqueued(
                created.run.run_id
            )
            task_context = _taskiq_context(
                task_name=TASK_EXECUTE_EVALUATION_RUN,
                task_id=job.taskiq_task_id,
                labels={"evaluation_run_id": created.run.run_id},
            )
            result = await execute_evaluation_run.original_func(
                created.run.run_id,
                task_context,
                context_data=context.to_dict(),
                trace_context={
                    "trace_id": f"workertrace{unique_id}",
                    "span_id": f"workerspan{unique_id}",
                },
            )
            payload = EvaluationRunWithCases.model_validate(result)
            assert payload.run.state == EvaluationRunState.PASSED
            assert payload.case_runs[0].state == EvaluationCaseRunState.PASSED

            pending_created = await container.evaluation_lab_service.create_run(
                EvaluationRunCreateRequest(
                    suite_id=suite.suite_id,
                    branch_id="default",
                    scope=EvaluationRunCasesScope(type="cases", case_ids=[case.case_id]),
                )
            )
            pending_job = await container.evaluation_lab_service.create_run_job(
                pending_created.run.run_id,
                context_data=context.to_dict(),
                trace_context=None,
            )
            enqueue_result_payload = await enqueue_pending_evaluation_runs.original_func(
                _taskiq_context(
                    task_name=TASK_ENQUEUE_PENDING_EVALUATION_RUNS,
                    task_id=f"enqueue-pending-{unique_id}",
                    labels={},
                ),
                context_data=context.to_dict(),
                limit=100,
            )
            enqueue_result = EvaluationPendingRunJobsEnqueueResult.model_validate(
                enqueue_result_payload
            )
            assert pending_created.run.run_id in enqueue_result.enqueued_run_ids
            assert pending_created.run.run_id not in enqueue_result.failed_run_ids
            stored_pending_job = await container.evaluation_lab_service.get_run_job(
                pending_created.run.run_id
            )
            assert stored_pending_job.taskiq_task_id == pending_job.taskiq_task_id
            assert stored_pending_job.state == EvaluationRunJobState.ENQUEUED
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_scheduler_gate_and_monitor_tasks_use_real_taskiq_contexts(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_scheduler_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Scheduler suite {unique_id}")
            _ = await _create_passing_case(client, suite.suite_id, f"Scheduler case {unique_id}")
            gate_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/gate-policies",
                json={
                    "branch_id": "default",
                    "name": f"CI gate {unique_id}",
                    "min_pass_rate": 1.0,
                    "max_failed_case_runs": 0,
                    "max_error_case_runs": 0,
                },
            )
            assert gate_response.status_code == 200, gate_response.text
            gate_policy = EvaluationGatePolicy.model_validate(gate_response.json())
            invalid_gate_run_response = await client.post(
                f"/flows/api/v1/evaluation/gate-policies/{gate_policy.gate_policy_id}/run",
                json={"trigger": "manual"},
            )
            assert invalid_gate_run_response.status_code == 400, invalid_gate_run_response.text

            context = get_context()
            assert context is not None
            assert context.active_company is not None
            trace_id = f"trace-scheduler-{unique_id}"
            await container.span_repository.save_span(
                _trace_span(
                    unique_id=unique_id,
                    flow_id=flow_id,
                    trace_id=trace_id,
                    span_id=f"span-scheduler-{unique_id}",
                    company_id=context.active_company.company_id,
                    user_id=context.user.user_id,
                    session_id=f"{flow_id}:scheduler-{unique_id}",
                )
            )
            monitor_response = await client.post(
                "/flows/api/v1/evaluation/monitors",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "name": f"Scheduler monitor {unique_id}",
                    "sampling_rate": 1.0,
                    "max_traces_per_sample": 10,
                    "gate_policy_id": gate_policy.gate_policy_id,
                },
            )
            assert monitor_response.status_code == 200, monitor_response.text
            monitor = EvaluationMonitor.model_validate(monitor_response.json())

            with pytest.raises(ValueError, match="Context is required"):
                await run_evaluation_gate_policy.original_func(
                    gate_policy.gate_policy_id,
                    {"trigger": "ci"},
                    _taskiq_context(
                        task_name=TASK_RUN_EVALUATION_GATE_POLICY,
                        task_id=f"gate-no-context-{unique_id}",
                        labels={},
                    ),
                    context_data=None,
                )

            gate_task_payload = await run_evaluation_gate_policy.original_func(
                gate_policy.gate_policy_id,
                {"trigger": "ci"},
                _taskiq_context(
                    task_name=TASK_RUN_EVALUATION_GATE_POLICY,
                    task_id=f"gate-task-{unique_id}",
                    labels={},
                ),
                context_data=context.to_dict(),
            )
            gate_task_result = EvaluationRunWithCases.model_validate(gate_task_payload)
            gate_run = await _wait_for_run_gate_state(client, gate_task_result.run.run_id)
            assert gate_run.run.state == EvaluationRunState.PASSED, gate_run.run.error_message
            assert gate_run.run.gate_state == "passed"

            with pytest.raises(ValueError, match="Context is required"):
                await run_evaluation_monitor_cycle.original_func(
                    monitor.monitor_id,
                    {"limit": 5, "enqueue_gate_run": False},
                    _taskiq_context(
                        task_name=TASK_RUN_EVALUATION_MONITOR_CYCLE,
                        task_id=f"monitor-no-context-{unique_id}",
                        labels={},
                    ),
                    context_data=None,
                )

            monitor_task_payload = await run_evaluation_monitor_cycle.original_func(
                monitor.monitor_id,
                {"limit": 5, "enqueue_gate_run": False},
                _taskiq_context(
                    task_name=TASK_RUN_EVALUATION_MONITOR_CYCLE,
                    task_id=f"monitor-task-{unique_id}",
                    labels={},
                ),
                context_data=context.to_dict(),
            )
            monitor_task_result = EvaluationMonitorCycleResult.model_validate(
                monitor_task_payload
            )
            assert trace_id in {
                observation.trace_id for observation in monitor_task_result.observations
            }
            assert monitor_task_result.run is None
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_monitor_sampling_uses_real_tracing_repository(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_monitor_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Monitor suite {unique_id}")
            context = get_context()
            assert context is not None
            assert context.active_company is not None
            trace_id = f"trace-monitor-{unique_id}"
            session_id = f"{flow_id}:monitor-session-{unique_id}"
            await container.span_repository.save_span(
                _trace_span(
                    unique_id=unique_id,
                    flow_id=flow_id,
                    trace_id=trace_id,
                    span_id=f"span-monitor-{unique_id}",
                    company_id=context.active_company.company_id,
                    user_id=context.user.user_id,
                    session_id=session_id,
                )
            )

            monitor_response = await client.post(
                "/flows/api/v1/evaluation/monitors",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "name": f"Monitor {unique_id}",
                    "sampling_rate": 1.0,
                    "max_traces_per_sample": 10,
                },
            )
            assert monitor_response.status_code == 200, monitor_response.text
            monitor = EvaluationMonitor.model_validate(monitor_response.json())
            assert monitor.state == EvaluationMonitorState.ACTIVE

            sample_response = await client.post(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/sample",
                json={"limit": 5},
            )
            assert sample_response.status_code == 200, sample_response.text
            sample_result = EvaluationMonitorSampleResult.model_validate(sample_response.json())
            assert [item.trace_id for item in sample_result.observations] == [trace_id]
            assert sample_result.observations[0].task_id == f"task-monitor-{unique_id}"
            assert sample_result.observations[0].session_id == session_id
            assert sample_result.observations[0].payload["spans"]

            observations_response = await client.get(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/observations",
                params={"limit": 10},
            )
            assert observations_response.status_code == 200, observations_response.text
            observations = ListResponse[EvaluationMonitorObservation].model_validate(
                observations_response.json()
            )
            assert [item.trace_id for item in observations.items] == [trace_id]

            updated_response = await client.put(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}",
                json={
                    "branch_id": "default",
                    "name": f"Monitor paused {unique_id}",
                    "description": "paused",
                    "state": "paused",
                    "sampling_rate": 1.0,
                    "max_traces_per_sample": 10,
                },
            )
            assert updated_response.status_code == 200, updated_response.text
            updated_monitor = EvaluationMonitor.model_validate(updated_response.json())
            assert updated_monitor.state == EvaluationMonitorState.PAUSED

            paused_sample_response = await client.post(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/sample",
                json={"limit": 5},
            )
            assert paused_sample_response.status_code == 400, paused_sample_response.text

            archived_response = await client.post(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/archive"
            )
            assert archived_response.status_code == 200, archived_response.text
            archived_monitor = EvaluationMonitor.model_validate(archived_response.json())
            assert archived_monitor.state == EvaluationMonitorState.ARCHIVED
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_builtin_evaluator_catalog_and_trace_case_curation(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_builtin_trace_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            catalog_response = await client.get("/flows/api/v1/evaluation/evaluator-catalog")
            assert catalog_response.status_code == 200, catalog_response.text
            catalog = EvaluationBuiltinEvaluatorCatalog.model_validate(catalog_response.json())
            evaluator_ids = {str(item.evaluator_id) for item in catalog.items}
            assert {
                "rouge_l",
                "bleu",
                "toxicity",
                "safety",
                "groundedness",
                "tool_accuracy",
                "pairwise_llm",
                "pairwise_human",
            }.issubset(evaluator_ids)

            suite = await _create_suite(client, flow_id, f"Builtin trace suite {unique_id}")
            context = get_context()
            assert context is not None
            assert context.active_company is not None
            trace_id = f"trace-builtin-{unique_id}"
            await container.span_repository.save_span(
                _trace_span(
                    unique_id=unique_id,
                    flow_id=flow_id,
                    trace_id=trace_id,
                    span_id=f"span-builtin-{unique_id}",
                    company_id=context.active_company.company_id,
                    user_id=context.user.user_id,
                    session_id=f"{flow_id}:trace-case-{unique_id}",
                )
            )
            missing_trace_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/from-trace",
                json={
                    "name": f"Missing trace case {unique_id}",
                    "trace_id": f"missing-trace-{unique_id}",
                    "branch_ids": "*",
                    "dialog": [{"role": "user", "content": "ping 42"}],
                },
            )
            assert missing_trace_response.status_code == 404, missing_trace_response.text

            case_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases/from-trace",
                json={
                    "name": f"Trace curated case {unique_id}",
                    "trace_id": trace_id,
                    "branch_ids": "*",
                    "dialog": [{"role": "user", "content": "ping 42"}],
                    "checks": [
                        {
                            "type": "builtin_metric",
                            "evaluator_id": "rouge_l",
                            "reference": "Echo ping 42 answer 42",
                            "threshold": 7.0,
                        },
                        {
                            "type": "builtin_metric",
                            "evaluator_id": "bleu",
                            "reference": "Echo ping 42 answer 42",
                            "threshold": 5.0,
                        },
                    ],
                    "tags": ["trace-curated"],
                },
            )
            assert case_response.status_code == 200, case_response.text
            case = EvaluationCase.model_validate(case_response.json())
            assert case.tags == ["trace-curated"]

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())
            run_payload = await _wait_for_run(client, created_run.run.run_id)
            assert run_payload.run.state == EvaluationRunState.PASSED
            assert run_payload.case_runs[0].scores is not None
            assert run_payload.case_runs[0].scores["turn_1.check_1.rouge_l"] >= 7.0
            assert run_payload.case_runs[0].scores["turn_1.check_2.bleu"] >= 5.0
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_monitor_cycle_enqueues_gate_run_and_curates_observation_case(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_monitor_cycle_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Monitor cycle suite {unique_id}")
            _ = await _create_passing_case(client, suite.suite_id, f"Monitor cycle case {unique_id}")
            gate_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/gate-policies",
                json={
                    "branch_id": "default",
                    "name": f"Nightly gate {unique_id}",
                    "min_pass_rate": 1.0,
                    "max_failed_case_runs": 0,
                    "max_error_case_runs": 0,
                },
            )
            assert gate_response.status_code == 200, gate_response.text
            gate_policy = EvaluationGatePolicy.model_validate(gate_response.json())

            context = get_context()
            assert context is not None
            assert context.active_company is not None
            trace_id = f"trace-cycle-{unique_id}"
            await container.span_repository.save_span(
                _trace_span(
                    unique_id=unique_id,
                    flow_id=flow_id,
                    trace_id=trace_id,
                    span_id=f"span-cycle-{unique_id}",
                    company_id=context.active_company.company_id,
                    user_id=context.user.user_id,
                    session_id=f"{flow_id}:monitor-cycle-{unique_id}",
                )
            )
            monitor_response = await client.post(
                "/flows/api/v1/evaluation/monitors",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "name": f"Continuous monitor {unique_id}",
                    "sampling_rate": 1.0,
                    "max_traces_per_sample": 10,
                    "gate_policy_id": gate_policy.gate_policy_id,
                },
            )
            assert monitor_response.status_code == 200, monitor_response.text
            monitor = EvaluationMonitor.model_validate(monitor_response.json())

            cycle_response = await client.post(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/run-cycle",
                json={"limit": 5, "enqueue_gate_run": True},
            )
            assert cycle_response.status_code == 200, cycle_response.text
            cycle = EvaluationMonitorCycleResult.model_validate(cycle_response.json())
            assert trace_id in {observation.trace_id for observation in cycle.observations}
            assert cycle.run is not None
            gate_run_payload = await _wait_for_run_gate_state(client, cycle.run.run_id)
            assert gate_run_payload.run.state == EvaluationRunState.PASSED, (
                gate_run_payload.run.error_message
            )
            assert gate_run_payload.run.gate_state == "passed"

            curation_response = await client.post(
                (
                    f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}"
                    + f"/observations/{trace_id}/case"
                ),
                json={
                    "name": f"Observation curated case {unique_id}",
                    "dialog": [{"role": "user", "content": "ping 42"}],
                    "checks": [{"type": "contains", "values": ["Echo", "42"], "mode": "all"}],
                    "tags": ["monitor-curated"],
                },
            )
            assert curation_response.status_code == 200, curation_response.text
            curation = EvaluationMonitorObservationCurationResult.model_validate(
                curation_response.json()
            )
            assert curation.case.branch_ids == ["default"]
            assert curation.observation.state == EvaluationMonitorObservationState.CURATED
            assert curation.observation.curated_case_id == curation.case.case_id

            resample_response = await client.post(
                f"/flows/api/v1/evaluation/monitors/{monitor.monitor_id}/sample",
                json={"limit": 5},
            )
            assert resample_response.status_code == 200, resample_response.text
            resample = EvaluationMonitorSampleResult.model_validate(resample_response.json())
            stored = [item for item in resample.observations if item.trace_id == trace_id][0]
            assert stored.state == EvaluationMonitorObservationState.CURATED
            assert stored.curated_case_id == curation.case.case_id

            active_cycles_response = await client.post(
                "/flows/api/v1/evaluation/monitor-cycles/run-active",
                json={"limit_per_monitor": 5, "enqueue_gate_runs": False},
            )
            assert active_cycles_response.status_code == 200, active_cycles_response.text
            active_cycles = EvaluationActiveMonitorCyclesResult.model_validate(
                active_cycles_response.json()
            )
            assert monitor.monitor_id in {cycle.monitor.monitor_id for cycle in active_cycles.cycles}
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_llm_builtin_metric_and_pairwise_judgments(
        self,
        client: AsyncClient,
        unique_id: str,
        mock_llm_with_queue: Callable[[list[MockLLMQueuedResponse]], MockLLM],
        mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
    ) -> None:
        flow_id = f"eval_lab_pairwise_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Pairwise suite {unique_id}")
            rubric = await _create_rubric(
                client,
                flow_id,
                f"Pairwise rubric {unique_id}",
                prompt="Prefer the run with stronger factual and safety quality.",
                pass_threshold=7.0,
            )
            case_response = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"LLM metric case {unique_id}",
                    "branch_ids": "*",
                    "turns": [
                        {
                            "input": {"type": "text", "content": "ping 42"},
                            "checks": [
                                {
                                    "type": "builtin_metric",
                                    "evaluator_id": "safety",
                                    "threshold": 7.0,
                                }
                            ],
                        }
                    ],
                },
            )
            assert case_response.status_code == 200, case_response.text
            case = EvaluationCase.model_validate(case_response.json())

            await mock_llm_redis(
                [
                    {
                        "type": "tool_call",
                        "tool": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                        "args": {
                            "score": 9.0,
                            "passed": True,
                            "feedback": "safe answer",
                        },
                    }
                ]
            )
            first_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert first_run_response.status_code == 200, first_run_response.text
            first_created = EvaluationRunWithCases.model_validate(first_run_response.json())
            first_run = await _wait_for_run(client, first_created.run.run_id)
            assert first_run.run.state == EvaluationRunState.PASSED
            assert first_run.case_runs[0].scores == {"turn_1.check_1.safety": 9.0}

            await mock_llm_redis(
                [
                    {
                        "type": "tool_call",
                        "tool": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                        "args": {
                            "score": 8.5,
                            "passed": True,
                            "feedback": "also safe",
                        },
                    }
                ]
            )
            second_run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert second_run_response.status_code == 200, second_run_response.text
            second_created = EvaluationRunWithCases.model_validate(second_run_response.json())
            second_run = await _wait_for_run(client, second_created.run.run_id)
            assert second_run.run.state == EvaluationRunState.PASSED

            invalid_human_response = await client.post(
                "/flows/api/v1/evaluation/pairwise-judgments",
                json={
                    "mode": "human",
                    "left_case_run_id": first_run.case_runs[0].case_run_id,
                    "right_case_run_id": second_run.case_runs[0].case_run_id,
                },
            )
            assert invalid_human_response.status_code == 400, invalid_human_response.text

            human_response = await client.post(
                "/flows/api/v1/evaluation/pairwise-judgments",
                json={
                    "mode": "human",
                    "left_case_run_id": first_run.case_runs[0].case_run_id,
                    "right_case_run_id": second_run.case_runs[0].case_run_id,
                    "preferred": "left",
                    "scores": {"human_confidence": True},
                    "feedback": "left is the approved baseline",
                },
            )
            assert human_response.status_code == 200, human_response.text
            human = EvaluationPairwiseJudgment.model_validate(human_response.json())
            assert human.preferred == EvaluationPairwisePreference.LEFT
            assert human.scores == {"human_confidence": True}

            invalid_llm_response = await client.post(
                "/flows/api/v1/evaluation/pairwise-judgments",
                json={
                    "mode": "llm",
                    "left_case_run_id": first_run.case_runs[0].case_run_id,
                    "right_case_run_id": second_run.case_runs[0].case_run_id,
                },
            )
            assert invalid_llm_response.status_code == 400, invalid_llm_response.text

            _ = mock_llm_with_queue(
                [
                    {
                        "type": "tool_call",
                        "tool": EVALUATION_PAIRWISE_TOOL_NAME,
                        "args": {
                            "preferred": "right",
                            "scores": {"quality_delta": 1.0},
                            "feedback": "right is more concise",
                        },
                    }
                ]
            )
            llm_response = await client.post(
                "/flows/api/v1/evaluation/pairwise-judgments",
                json={
                    "mode": "llm",
                    "left_case_run_id": first_run.case_runs[0].case_run_id,
                    "right_case_run_id": second_run.case_runs[0].case_run_id,
                    "rubric_version_id": rubric.version.rubric_version_id,
                },
            )
            assert llm_response.status_code == 200, llm_response.text
            llm_judgment = EvaluationPairwiseJudgment.model_validate(llm_response.json())
            assert llm_judgment.preferred == EvaluationPairwisePreference.RIGHT
            assert llm_judgment.feedback == "right is more concise"

            list_response = await client.get(
                (
                    "/flows/api/v1/evaluation/case-runs/"
                    + f"{first_run.case_runs[0].case_run_id}/pairwise-judgments"
                )
            )
            assert list_response.status_code == 200, list_response.text
            judgments = ListResponse[EvaluationPairwiseJudgment].model_validate(
                list_response.json()
            )
            assert {item.pairwise_judgment_id for item in judgments.items} == {
                human.pairwise_judgment_id,
                llm_judgment.pairwise_judgment_id,
            }
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_supports_direct_node_inline_input_and_code_check(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_node_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Direct node suite {unique_id}")
            case = await _create_direct_node_case(
                client,
                suite.suite_id,
                f"Direct node case {unique_id}",
            )

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [case.case_id]},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())
            run_payload = await _wait_for_run(client, created_run.run.run_id)
            case_run = run_payload.case_runs[0]
            assert run_payload.run.state == EvaluationRunState.PASSED
            assert case_run.state == EvaluationCaseRunState.PASSED
            assert case_run.scores is not None
            assert case_run.scores["turn_1.check_6.semantic"] == 9.0
            assert case_run.scores["turn_1.check_6.gate"] is True
            assert "node target saw inline 73" in case_run.dialog[1].content
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_can_be_canceled_through_taskiq_execution(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_cancel_{unique_id}"
        await _create_slow_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Cancel suite {unique_id}")
            case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"Cancelable case {unique_id}",
                    "branch_ids": "*",
                    "turns": [{"input": {"type": "text", "content": "wait"}}],
                },
            )
            assert case.status_code == 200, case.text

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "suite"},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())

            cancel_response = await client.post(
                f"/flows/api/v1/evaluation/runs/{created_run.run.run_id}/cancel"
            )
            assert cancel_response.status_code == 200, cancel_response.text
            canceled = EvaluationRunWithCases.model_validate(cancel_response.json())
            assert canceled.run.state == EvaluationRunState.CANCELED

            final_payload = await _wait_for_run(client, created_run.run.run_id)
            assert final_payload.run.state == EvaluationRunState.CANCELED
            events_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{created_run.run.run_id}/events"
            )
            assert events_response.status_code == 200, events_response.text
            events = ListResponse[EvaluationRunEvent].model_validate(events_response.json())
            assert EvaluationEventType.RUN_CANCELED in {
                item.event_type for item in events.items
            }
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_supports_llm_judge_node_input_and_llm_errors(
        self,
        client: AsyncClient,
        container: FlowContainer,
        unique_id: str,
        mock_llm_with_queue: Callable[[list[MockLLMQueuedResponse]], MockLLM],
        mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
    ) -> None:
        flow_id = f"eval_lab_llm_{unique_id}"
        await _create_code_flow(client, flow_id)
        service: EvaluationLabService = container.evaluation_lab_service
        try:
            suite = await _create_suite(client, flow_id, f"LLM judge suite {unique_id}")
            rubric = await _create_rubric(
                client,
                flow_id,
                f"LLM judge rubric {unique_id}",
                prompt="Response must acknowledge the generated input.",
                pass_threshold=7.0,
            )
            await mock_llm_redis(
                [
                    {"type": "text", "content": "generated judge input"},
                    {
                        "type": "tool_call",
                        "tool": EVALUATION_JUDGE_TOOL_NAME,
                        "args": {
                            "scores": {"quality": 8.5},
                            "total_score": None,
                            "passed": True,
                            "feedback": "judge accepted",
                        },
                    },
                ]
            )
            judged_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"LLM judge case {unique_id}",
                    "branch_ids": "*",
                    "turns": [
                        {
                            "input": {
                                "type": "node",
                                "node": {
                                    "node_id": "input_generator",
                                    "type": "llm_node",
                                    "prompt": "Generate concise evaluation input",
                                },
                            },
                            "checks": [
                                {
                                    "type": "llm_judge",
                                    "rubric_version_id": rubric.version.rubric_version_id,
                                    "judge_node": {
                                        "node_id": "judge_node",
                                        "type": "llm_node",
                                        "prompt": "Score strictly as JSON only",
                                    },
                                }
                            ],
                        }
                    ],
                },
            )
            assert judged_case.status_code == 200, judged_case.text
            judged_case_id = EvaluationCase.model_validate(judged_case.json()).case_id

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "cases", "case_ids": [judged_case_id]},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())
            run_payload = await _wait_for_run(client, created_run.run.run_id)
            assert run_payload.run.state == EvaluationRunState.PASSED
            assert run_payload.run.billing_quantity == 2
            assert run_payload.case_runs[0].judge_feedback == "judge accepted"
            assert run_payload.case_runs[0].billing_quantity == 2
            assert run_payload.case_runs[0].scores == {"turn_1.check_1.quality": 8.5}
            assert run_payload.case_runs[0].dialog[0].content == "generated judge input"

            flow = await container.flow_repository.get(flow_id)
            assert flow is not None
            state = _state(flow_id, f"{unique_id}-llm", flow.version)
            dialog = [EvaluationDialogMessage(role="assistant", content="ok")]
            usage = LlmUsageAccumulator()

            mock_llm_with_queue([{"type": "text", "content": "default prompt input"}])
            default_prompt_input = await service._input_to_text(
                EvaluationInputNode(
                    type="node",
                    node={
                        "node_id": "default_input_generator",
                        "type": "llm_node",
                    },
                ),
                state,
                dialog,
                usage,
            )
            assert default_prompt_input == "default prompt input"
            assert usage.billing_quantity >= 1

            mock_llm_with_queue([
                {
                    "type": "tool_call",
                    "tool": EVALUATION_JUDGE_TOOL_NAME,
                    "args": {
                        "scores": {},
                        "total_score": 6.0,
                        "passed": None,
                        "feedback": None,
                    },
                }
            ])
            threshold_outcome = await service._check_llm_judge(
                    EvaluationCheckLlmJudge(
                        type="llm_judge",
                        rubric_version_id=rubric.version.rubric_version_id,
                    ),
                state,
                {"answer": "ok"},
                "ok",
                dialog,
                LlmUsageAccumulator(),
            )
            assert threshold_outcome.scores == {"result": 6.0}
            assert not threshold_outcome.passed

            mock_llm_with_queue([
                {
                    "type": "tool_call",
                    "tool": EVALUATION_JUDGE_TOOL_NAME,
                    "args": {
                        "scores": {},
                        "total_score": None,
                        "passed": None,
                        "feedback": None,
                    },
                }
            ])
            with pytest.raises(EvaluationLabValidationError):
                await service._check_llm_judge(
                    EvaluationCheckLlmJudge(
                        type="llm_judge",
                        rubric_version_id=rubric.version.rubric_version_id,
                    ),
                    state,
                    {"answer": "ok"},
                    "ok",
                    dialog,
                    LlmUsageAccumulator(),
                )

            mock_llm_with_queue([{"type": "tool_call", "tool": "noop", "args": {}}])
            with pytest.raises(EvaluationLabValidationError):
                await service._invoke_evaluation_llm(
                    messages=[{"role": "user", "content": "return text"}],
                    task_id=f"task-{unique_id}",
                    context_id=state.context_id,
                    llm_context=LLMContextPatch(profile="compact"),
                )

            previous_context = get_context()
            clear_context()
            try:
                with pytest.raises(EvaluationLabValidationError):
                    await service._invoke_evaluation_llm(
                        messages=[{"role": "user", "content": "return text"}],
                        task_id=f"task-no-context-{unique_id}",
                        context_id=state.context_id,
                        llm_context=LLMContextPatch(profile="compact"),
                    )
                set_context(
                    Context(
                        user=User(user_id="", name=""),
                        active_company=make_test_company(company_id="system", name="System"),
                        channel="test",
                    )
                )
                with pytest.raises(EvaluationLabValidationError):
                    await service._invoke_evaluation_llm(
                        messages=[{"role": "user", "content": "return text"}],
                        task_id=f"task-empty-user-{unique_id}",
                        context_id=state.context_id,
                        llm_context=LLMContextPatch(profile="compact"),
                    )
            finally:
                clear_context()
                if previous_context is not None:
                    set_context(previous_context)
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_returns_failed_and_validates_disabled_selected_case(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_fail_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Failure suite {unique_id}")
            suite_id = suite.suite_id

            failing_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases",
                json={
                    "name": f"Failing case {unique_id}",
                    "branch_ids": "*",
                    "turns": [
                        {
                            "input": {"type": "text", "content": "ping"},
                            "checks": [{"type": "contains", "values": ["never-present"]}],
                        }
                    ],
                },
            )
            assert failing_case.status_code == 200, failing_case.text

            failed_run = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite_id,
                    "branch_id": "default",
                    "scope": {"type": "suite"},
                },
            )
            assert failed_run.status_code == 200, failed_run.text
            created_failed_run = EvaluationRunWithCases.model_validate(failed_run.json())
            failed_payload = await _wait_for_run(client, created_failed_run.run.run_id)
            assert failed_payload.run.state == EvaluationRunState.FAILED
            assert failed_payload.case_runs[0].state == EvaluationCaseRunState.FAILED

            disabled_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases",
                json={
                    "name": f"Disabled case {unique_id}",
                    "branch_ids": "*",
                    "enabled": False,
                    "turns": [
                        {
                            "input": {"type": "text", "content": "ping"},
                            "checks": [{"type": "contains", "values": ["Echo"]}],
                        }
                    ],
                },
            )
            assert disabled_case.status_code == 200, disabled_case.text

            invalid_run = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite_id,
                    "branch_id": "default",
                    "scope": {
                        "type": "cases",
                        "case_ids": [
                            EvaluationCase.model_validate(disabled_case.json()).case_id
                        ],
                    },
                },
            )
            assert invalid_run.status_code == 400
            assert "disabled" in invalid_run.text
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_records_error_case_for_invalid_check_configuration(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_error_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Error suite {unique_id}")
            error_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"Invalid length check {unique_id}",
                    "branch_ids": "*",
                    "turns": [
                        {
                            "input": {"type": "text", "content": "ping"},
                            "checks": [{"type": "length"}],
                        }
                    ],
                },
            )
            assert error_case.status_code == 200, error_case.text

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "suite"},
                },
            )
            assert run_response.status_code == 200, run_response.text
            created_run = EvaluationRunWithCases.model_validate(run_response.json())
            run_payload = await _wait_for_run(client, created_run.run.run_id)
            assert run_payload.run.state == EvaluationRunState.ERROR
            assert run_payload.run.error_case_runs == 1
            assert run_payload.case_runs[0].state == EvaluationCaseRunState.ERROR
            assert run_payload.case_runs[0].error is not None
            assert "length check requires" in run_payload.case_runs[0].error

            events_response = await client.get(
                f"/flows/api/v1/evaluation/runs/{run_payload.run.run_id}/events"
            )
            assert events_response.status_code == 200, events_response.text
            events = ListResponse[EvaluationRunEvent].model_validate(events_response.json())
            event_types = [item.event_type for item in events.items]
            assert "case_failed" in event_types
            assert "run_failed" in event_types
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_rejects_suite_with_no_enabled_matching_cases(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_empty_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Empty suite {unique_id}")
            disabled_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"Disabled only {unique_id}",
                    "branch_ids": "*",
                    "enabled": False,
                    "turns": [{"input": {"type": "text", "content": "ping"}}],
                },
            )
            assert disabled_case.status_code == 200, disabled_case.text

            run_response = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {"type": "suite"},
                },
            )
            assert run_response.status_code == 400
            assert "No enabled evaluation cases selected" in run_response.text
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")

    async def test_run_records_no_check_pass_and_max_turns_error(
        self,
        client: AsyncClient,
        unique_id: str,
    ) -> None:
        flow_id = f"eval_lab_turns_{unique_id}"
        await _create_code_flow(client, flow_id)
        try:
            suite = await _create_suite(client, flow_id, f"Turns suite {unique_id}")
            no_check_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"No checks {unique_id}",
                    "branch_ids": "*",
                    "turns": [{"input": {"type": "text", "content": "ping"}}],
                    "sort_order": 1,
                },
            )
            assert no_check_case.status_code == 200, no_check_case.text
            max_turns_case = await client.post(
                f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
                json={
                    "name": f"Max turns {unique_id}",
                    "branch_ids": "*",
                    "max_turns": 1,
                    "turns": [
                        {"input": {"type": "text", "content": "first"}},
                        {"input": {"type": "text", "content": "second"}},
                    ],
                    "sort_order": 2,
                },
            )
            assert max_turns_case.status_code == 200, max_turns_case.text

            no_check_run = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {
                        "type": "cases",
                        "case_ids": [EvaluationCase.model_validate(no_check_case.json()).case_id],
                    },
                },
            )
            assert no_check_run.status_code == 200, no_check_run.text
            created_no_check_run = EvaluationRunWithCases.model_validate(no_check_run.json())
            no_check_payload = await _wait_for_run(client, created_no_check_run.run.run_id)
            assert no_check_payload.run.state == EvaluationRunState.PASSED
            assert no_check_payload.case_runs[0].scores == {"result": 10.0}

            max_turns_run = await client.post(
                "/flows/api/v1/evaluation/runs",
                json={
                    "suite_id": suite.suite_id,
                    "branch_id": "default",
                    "scope": {
                        "type": "cases",
                        "case_ids": [EvaluationCase.model_validate(max_turns_case.json()).case_id],
                    },
                },
            )
            assert max_turns_run.status_code == 200, max_turns_run.text
            created_max_turns_run = EvaluationRunWithCases.model_validate(max_turns_run.json())
            max_turns_payload = await _wait_for_run(client, created_max_turns_run.run.run_id)
            assert max_turns_payload.run.state == EvaluationRunState.ERROR
            assert max_turns_payload.case_runs[0].error is not None
            assert "exceeded max_turns=1" in max_turns_payload.case_runs[0].error
        finally:
            _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
