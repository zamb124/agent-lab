"""Builtin metrics — deterministic rouge/bleu thresholds + LLM metrics via MockLLM."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from apps.flows.src.evaluation.lab_service import EVALUATION_BUILTIN_METRIC_TOOL_NAME
from apps.flows.src.models.evaluation_lab import EvaluationCaseRunState, EvaluationRunState
from core.clients.llm.mock import MockLLMQueuedResponse
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    builtin_metric_check,
    create_case,
    create_echo_flow,
    create_suite,
    ensure_judge_and_tester_nodes,
    first_case_run,
    run_case_and_wait,
    text_turn,
)


@pytest.mark.asyncio
async def test_rouge_l_pass_and_fail_threshold(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_rouge_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Rouge suite {unique_id}")
        pass_case = await create_case(
            client,
            suite.suite_id,
            name=f"Rouge pass {unique_id}",
            turns=[
                text_turn(
                    "ping 42",
                    [
                        builtin_metric_check(
                            "rouge_l",
                            reference="Echo: ping 42 / answer=42",
                            threshold=7.0,
                        )
                    ],
                )
            ],
        )
        pass_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=pass_case.case_id
        )
        assert_case_run_state(first_case_run(pass_payload), EvaluationCaseRunState.PASSED)
        pass_scores = first_case_run(pass_payload).scores
        assert pass_scores is not None
        assert pass_scores["turn_1.check_1.rouge_l"] >= 7.0

        fail_case = await create_case(
            client,
            suite.suite_id,
            name=f"Rouge fail {unique_id}",
            turns=[
                text_turn(
                    "ping 42",
                    [
                        builtin_metric_check(
                            "rouge_l",
                            reference="completely unrelated reference text",
                            threshold=9.5,
                        )
                    ],
                )
            ],
        )
        fail_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=fail_case.case_id
        )
        assert_case_run_state(first_case_run(fail_payload), EvaluationCaseRunState.FAILED)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_bleu_pass_and_fail_threshold(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_bleu_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Bleu suite {unique_id}")
        pass_case = await create_case(
            client,
            suite.suite_id,
            name=f"Bleu pass {unique_id}",
            turns=[
                text_turn(
                    "ping 42",
                    [
                        builtin_metric_check(
                            "bleu",
                            reference="Echo: ping 42 / answer=42",
                            threshold=5.0,
                        )
                    ],
                )
            ],
        )
        pass_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=pass_case.case_id
        )
        assert_case_run_state(first_case_run(pass_payload), EvaluationCaseRunState.PASSED)

        fail_case = await create_case(
            client,
            suite.suite_id,
            name=f"Bleu fail {unique_id}",
            turns=[
                text_turn(
                    "ping 42",
                    [
                        builtin_metric_check(
                            "bleu",
                            reference="zzzz unrelated",
                            threshold=9.9,
                        )
                    ],
                )
            ],
        )
        fail_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=fail_case.case_id
        )
        assert_case_run_state(first_case_run(fail_payload), EvaluationCaseRunState.FAILED)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_llm_safety_metric_pass_fail_and_judge_node(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_builtin_llm_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"Builtin LLM suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Safety metric {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [
                        builtin_metric_check(
                            "safety",
                            threshold=7.0,
                            judge_node_id="eval_judge",
                        )
                    ],
                )
            ],
        )

        await mock_llm_redis(
            [
                {
                    "type": "tool_call",
                    "tool": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                    "args": {
                        "score": 9.0,
                        "passed": True,
                        "feedback": "safe",
                    },
                }
            ]
        )
        pass_payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert pass_payload.run.state == EvaluationRunState.PASSED
        assert first_case_run(pass_payload).scores == {"turn_1.check_1.safety": 9.0}

        await mock_llm_redis(
            [
                {
                    "type": "tool_call",
                    "tool": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                    "args": {
                        "score": 2.0,
                        "passed": False,
                        "feedback": "unsafe",
                    },
                }
            ]
        )
        fail_payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert_case_run_state(first_case_run(fail_payload), EvaluationCaseRunState.FAILED)
        assert first_case_run(fail_payload).judge_feedback == "unsafe"
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "evaluator_id",
    ["toxicity", "groundedness", "answer_relevance", "tool_accuracy"],
)
async def test_llm_builtin_metric_ids_accept_tool(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
    evaluator_id: str,
) -> None:
    flow_id = f"eval_metric_{evaluator_id}_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"{evaluator_id} suite {unique_id}")
        reference = "context" if evaluator_id != "toxicity" else None
        case = await create_case(
            client,
            suite.suite_id,
            name=f"{evaluator_id} case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [
                        builtin_metric_check(
                            evaluator_id,
                            reference=reference,
                            threshold=7.0,
                        )
                    ],
                )
            ],
        )
        await mock_llm_redis(
            [
                {
                    "type": "tool_call",
                    "tool": EVALUATION_BUILTIN_METRIC_TOOL_NAME,
                    "args": {
                        "score": 8.0,
                        "passed": True,
                        "feedback": f"{evaluator_id} ok",
                    },
                }
            ]
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.scores is not None
        assert f"turn_1.check_1.{evaluator_id}" in case_run.scores
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
