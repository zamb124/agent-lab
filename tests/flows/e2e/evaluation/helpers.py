"""Shared helpers for Evaluation Lab E2E matrix tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from httpx2 import AsyncClient

from apps.flows.src.evaluation.lab_service import EVALUATION_JUDGE_TOOL_NAME
from apps.flows.src.models.evaluation_lab import (
    EvaluationCase,
    EvaluationCaseRun,
    EvaluationCaseRunState,
    EvaluationRubricWithVersion,
    EvaluationRunState,
    EvaluationRunWithCases,
    EvaluationSuite,
)
from core.clients.llm.mock import MockLLMQueuedResponse

JudgeSeedFn = Callable[[list[MockLLMQueuedResponse]], Awaitable[None]]


async def create_echo_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Evaluation Lab Matrix Flow",
            "entry": "echo",
            "nodes": {
                "echo": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    content = state['content']\n"
                        "    state['answer'] = '42'\n"
                        "    state['structured_output'] = {'answer': '42', 'ok': True}\n"
                        "    state['response'] = f'Echo: {content} / answer=42'\n"
                        "    return state\n"
                    ),
                }
            },
            "edges": [{"from_node": "echo", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def put_flow_nodes(
    client: AsyncClient,
    flow_id: str,
    *,
    extra_nodes: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    get_response = await client.get(f"/flows/api/v1/flows/{flow_id}")
    assert get_response.status_code == 200, get_response.text
    flow = get_response.json()
    nodes = dict(flow.get("nodes") or {})
    for node_id, node_config in extra_nodes.items():
        nodes[node_id] = dict(node_config)
    put_response = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        json={
            "flow_id": flow_id,
            "name": flow["name"],
            "description": flow.get("description") or "",
            "entry": flow["entry"],
            "nodes": nodes,
            "edges": flow.get("edges") or [],
            "variables": {},
            "tags": flow.get("tags") or [],
            "branches": flow.get("branches") or {},
        },
    )
    assert put_response.status_code == 200, put_response.text
    return put_response.json()


async def ensure_judge_and_tester_nodes(
    client: AsyncClient,
    flow_id: str,
    *,
    judge_prompt: str = "Score strictly. Call the judgment tool exactly once.",
    tester_prompt: str = "Generate one short user message.",
    judge_llm: Mapping[str, object] | None = None,
    tester_llm: Mapping[str, object] | None = None,
) -> None:
    judge_node: dict[str, object] = {
        "type": "llm_node",
        "name": "Evaluation Judge",
        "prompt": judge_prompt,
        "store": {"evaluation_role": "judge"},
    }
    if judge_llm is not None:
        judge_node["llm"] = dict(judge_llm)
    tester_node: dict[str, object] = {
        "type": "llm_node",
        "name": "Evaluation Tester",
        "prompt": tester_prompt,
        "store": {"evaluation_role": "tester"},
    }
    if tester_llm is not None:
        tester_node["llm"] = dict(tester_llm)
    await put_flow_nodes(
        client,
        flow_id,
        extra_nodes={
            "eval_judge": judge_node,
            "eval_tester": tester_node,
        },
    )


async def create_suite(client: AsyncClient, flow_id: str, name: str) -> EvaluationSuite:
    response = await client.post(
        "/flows/api/v1/evaluation/suites",
        json={
            "flow_id": flow_id,
            "name": name,
            "description": "Evaluation matrix suite",
            "tags": ["e2e", "matrix"],
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationSuite.model_validate(response.json())


async def create_rubric(
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
            "description": "Matrix rubric",
            "tags": ["rubric"],
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationRubricWithVersion.model_validate(response.json())


async def create_rubric_version(
    client: AsyncClient,
    rubric_id: str,
    *,
    prompt: str,
    pass_threshold: float,
) -> dict[str, object]:
    response = await client.post(
        f"/flows/api/v1/evaluation/rubrics/{rubric_id}/versions",
        json={"prompt": prompt, "pass_threshold": pass_threshold},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("rubric version response must be object")
    return payload


async def create_case(
    client: AsyncClient,
    suite_id: str,
    *,
    name: str,
    turns: Sequence[Mapping[str, object]],
    max_turns: int = 10,
    enabled: bool = True,
    tags: Sequence[str] | None = None,
) -> EvaluationCase:
    response = await client.post(
        f"/flows/api/v1/evaluation/suites/{suite_id}/cases",
        json={
            "name": name,
            "description": name,
            "branch_ids": "*",
            "target": {"type": "flow"},
            "turns": list(turns),
            "max_turns": max_turns,
            "enabled": enabled,
            "tags": list(tags) if tags is not None else ["matrix"],
            "sort_order": 0,
        },
    )
    assert response.status_code == 200, response.text
    return EvaluationCase.model_validate(response.json())


async def get_case(client: AsyncClient, suite_id: str, case_id: str) -> EvaluationCase:
    response = await client.get(f"/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return EvaluationCase.model_validate(response.json())


async def create_run(
    client: AsyncClient,
    *,
    suite_id: str,
    case_ids: Sequence[str] | None = None,
    trials: int = 1,
    max_concurrency: int = 1,
    branch_id: str = "default",
) -> EvaluationRunWithCases:
    scope: dict[str, object]
    if case_ids is None:
        scope = {"type": "suite"}
    else:
        scope = {"type": "cases", "case_ids": list(case_ids)}
    payload = {
        "suite_id": suite_id,
        "branch_id": branch_id,
        "scope": scope,
        "trials": trials,
        "max_concurrency": max_concurrency,
    }
    last_error = "evaluation run was not created"
    for attempt in range(5):
        run_response = await client.post("/flows/api/v1/evaluation/runs", json=payload)
        if run_response.status_code != 200:
            last_error = run_response.text
            await asyncio.sleep(0.15 * (attempt + 1))
            continue
        created = EvaluationRunWithCases.model_validate(run_response.json())
        if created.run.state == EvaluationRunState.QUEUED:
            return created
        last_error = f"unexpected evaluation run state: {created.run.state}"
        await asyncio.sleep(0.15 * (attempt + 1))
    raise AssertionError(last_error)


async def wait_for_run(
    client: AsyncClient,
    run_id: str,
    *,
    timeout_seconds: float = 60.0,
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


async def run_case_and_wait(
    client: AsyncClient,
    *,
    suite_id: str,
    case_id: str,
    trials: int = 1,
    max_concurrency: int = 1,
) -> EvaluationRunWithCases:
    created = await create_run(
        client,
        suite_id=suite_id,
        case_ids=[case_id],
        trials=trials,
        max_concurrency=max_concurrency,
    )
    return await wait_for_run(client, created.run.run_id)


def text_turn(content: str, checks: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "input": {"type": "text", "content": content},
        "checks": list(checks),
    }


def contains_check(
    *values: str,
    mode: str = "any",
    case_sensitive: bool = False,
) -> dict[str, object]:
    return {
        "type": "contains",
        "source": "response",
        "values": list(values),
        "mode": mode,
        "case_sensitive": case_sensitive,
        "state_path": None,
    }


def not_contains_check(*values: str, case_sensitive: bool = False) -> dict[str, object]:
    return {
        "type": "not_contains",
        "source": "response",
        "values": list(values),
        "case_sensitive": case_sensitive,
        "state_path": None,
    }


def regex_check(pattern: str, *, ignore_case: bool = True) -> dict[str, object]:
    return {
        "type": "regex",
        "source": "response",
        "pattern": pattern,
        "ignore_case": ignore_case,
        "state_path": None,
    }


def length_check(
    *,
    min_chars: int | None = None,
    max_chars: int | None = None,
) -> dict[str, object]:
    return {
        "type": "length",
        "source": "response",
        "min_chars": min_chars,
        "max_chars": max_chars,
        "state_path": None,
    }


def state_path_check(
    path: str,
    operator: str,
    value: object = None,
) -> dict[str, object]:
    return {
        "type": "state_path",
        "path": path,
        "operator": operator,
        "value": value,
    }


def json_schema_check(
    schema: Mapping[str, object],
    *,
    source: str = "state",
    state_path: str | None = "structured_output",
) -> dict[str, object]:
    return {
        "type": "json_schema",
        "source": source,
        "state_path": state_path,
        "json_schema": dict(schema),
    }


def trace_assertion_check(assertion: str, value: str) -> dict[str, object]:
    return {
        "type": "trace_assertion",
        "assertion": assertion,
        "value": value,
    }


def code_check(
    source: str,
    *,
    language: str = "python",
) -> dict[str, object]:
    return {
        "type": "code",
        "language": language,
        "source": source,
        "entrypoint": None,
    }


def builtin_metric_check(
    evaluator_id: str,
    *,
    reference: str | None = None,
    threshold: float | None = None,
    judge_node_id: str | None = None,
) -> dict[str, object]:
    return {
        "type": "builtin_metric",
        "evaluator_id": evaluator_id,
        "source": "response",
        "state_path": None,
        "reference": reference,
        "threshold": threshold,
        "judge_node_id": judge_node_id,
        "judge_node": None,
    }


def judge_check(
    rubric_version_id: str,
    *,
    judge_node_id: str | None = "eval_judge",
) -> dict[str, object]:
    return {
        "type": "llm_judge",
        "rubric_version_id": rubric_version_id,
        "judge_node_id": judge_node_id,
        "judge_node": None,
    }


def inline_code_turn(
    source: str,
    checks: Sequence[Mapping[str, object]],
    *,
    language: str = "python",
) -> dict[str, object]:
    return {
        "input": {
            "type": "inline_code",
            "language": language,
            "source": source,
            "entrypoint": None,
        },
        "checks": list(checks),
    }


def node_input_turn(
    checks: Sequence[Mapping[str, object]],
    *,
    node_id: str | None = None,
    node: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "input": {
            "type": "node",
            "node_id": node_id,
            "node": dict(node) if node is not None else None,
        },
        "checks": list(checks),
    }


def judge_tool_response(
    *,
    scores: Mapping[str, float] | None = None,
    total_score: float | None = None,
    passed: bool | None = True,
    feedback: str | None = "ok",
) -> MockLLMQueuedResponse:
    return {
        "type": "tool_call",
        "tool": EVALUATION_JUDGE_TOOL_NAME,
        "args": {
            "scores": dict(scores) if scores is not None else {},
            "total_score": total_score,
            "passed": passed,
            "feedback": feedback,
        },
    }


async def seed_judge_tool(
    mock_llm_redis: JudgeSeedFn,
    *,
    scores: Mapping[str, float] | None = None,
    total_score: float | None = None,
    passed: bool | None = True,
    feedback: str | None = "ok",
    prepend: Sequence[MockLLMQueuedResponse] | None = None,
) -> None:
    queue: list[MockLLMQueuedResponse] = list(prepend) if prepend is not None else []
    queue.append(
        judge_tool_response(
            scores=scores,
            total_score=total_score,
            passed=passed,
            feedback=feedback,
        )
    )
    await mock_llm_redis(queue)


def first_case_run(payload: EvaluationRunWithCases) -> EvaluationCaseRun:
    if len(payload.case_runs) == 0:
        raise AssertionError("expected at least one case run")
    return payload.case_runs[0]


def assert_score_keys(case_run: EvaluationCaseRun, expected: Mapping[str, float]) -> None:
    scores = case_run.scores
    assert scores is not None, f"case_run.scores is None (state={case_run.state})"
    for key, value in expected.items():
        assert key in scores, f"missing score key {key} in {scores}"
        assert scores[key] == value


def assert_case_stores_ids_only(case: EvaluationCase) -> None:
    for turn in case.turns:
        input_payload = turn.input
        if input_payload.type == "node":
            assert input_payload.node_id is not None
            assert input_payload.node is None
        for check in turn.checks:
            if check.type == "llm_judge":
                assert check.judge_node is None
                assert check.judge_node_id is not None


def assert_case_run_state(
    case_run: EvaluationCaseRun,
    expected: EvaluationCaseRunState,
) -> None:
    assert case_run.state == expected, (
        f"case_run.state={case_run.state} error={case_run.error} scores={case_run.scores}"
    )


def json_object(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")
    return value
