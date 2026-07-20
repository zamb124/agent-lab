"""LLM judge scoring contract — full run E2E with MockLLM tool calls."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient

from apps.flows.src.evaluation.lab_service import EVALUATION_JUDGE_TOOL_NAME
from apps.flows.src.models.evaluation_lab import (
    EvaluationCase,
    EvaluationCaseRunState,
    EvaluationRubricWithVersion,
    EvaluationRunState,
    EvaluationSuite,
)
from core.clients.llm.mock import MockLLMQueuedResponse
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    assert_score_keys,
    contains_check,
    create_case,
    create_echo_flow,
    create_rubric,
    create_rubric_version,
    create_suite,
    ensure_judge_and_tester_nodes,
    first_case_run,
    judge_check,
    run_case_and_wait,
    seed_judge_tool,
    text_turn,
)


@dataclass(frozen=True)
class JudgeHarness:
    client: AsyncClient
    flow_id: str
    suite: EvaluationSuite
    rubric: EvaluationRubricWithVersion
    case: EvaluationCase


@pytest.fixture
async def judge_harness(client: AsyncClient, unique_id: str) -> AsyncIterator[JudgeHarness]:
    flow_id = f"eval_judge_{unique_id}"
    await create_echo_flow(client, flow_id)
    await ensure_judge_and_tester_nodes(client, flow_id)
    suite = await create_suite(client, flow_id, f"Judge suite {unique_id}")
    rubric = await create_rubric(
        client,
        flow_id,
        f"Judge rubric {unique_id}",
        pass_threshold=7.0,
    )
    case = await create_case(
        client,
        suite.suite_id,
        name=f"Judge case {unique_id}",
        turns=[
            text_turn(
                "ping",
                [judge_check(rubric.version.rubric_version_id, judge_node_id="eval_judge")],
            )
        ],
    )
    try:
        yield JudgeHarness(
            client=client,
            flow_id=flow_id,
            suite=suite,
            rubric=rubric,
            case=case,
        )
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_c1_scores_passed_true_feedback(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={"quality": 9.0},
        passed=True,
        feedback="ok",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert payload.run.state == EvaluationRunState.PASSED
    case_run = first_case_run(payload)
    assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
    assert_score_keys(case_run, {"turn_1.check_1.quality": 9.0})
    assert case_run.judge_feedback == "ok"


@pytest.mark.asyncio
async def test_c2_explicit_passed_false_beats_high_score(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={"quality": 9.5},
        passed=False,
        feedback="forced fail",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert payload.run.state == EvaluationRunState.FAILED
    case_run = first_case_run(payload)
    assert_case_run_state(case_run, EvaluationCaseRunState.FAILED)
    assert case_run.judge_feedback == "forced fail"


@pytest.mark.asyncio
async def test_c3_passed_null_above_threshold_passes(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={"quality": 8.0},
        passed=None,
        feedback="threshold pass",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert payload.run.state == EvaluationRunState.PASSED
    assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.PASSED)


@pytest.mark.asyncio
async def test_c4_passed_null_below_threshold_fails(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={"quality": 6.0},
        passed=None,
        feedback="threshold fail",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert payload.run.state == EvaluationRunState.FAILED
    assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_c5_empty_scores_uses_total_score(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={},
        total_score=8.0,
        passed=None,
        feedback="total only",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    case_run = first_case_run(payload)
    assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
    assert_score_keys(case_run, {"turn_1.check_1.result": 8.0})


@pytest.mark.asyncio
async def test_c6_empty_scores_and_null_total_errors(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={},
        total_score=None,
        passed=None,
        feedback=None,
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    case_run = first_case_run(payload)
    assert_case_run_state(case_run, EvaluationCaseRunState.ERROR)
    assert case_run.error is not None


@pytest.mark.asyncio
async def test_c7_wrong_tool_or_freeform_text_errors(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await mock_llm_redis([{"type": "text", "content": "not a tool call"}])
    text_payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert_case_run_state(first_case_run(text_payload), EvaluationCaseRunState.ERROR)

    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "noop",
                "args": {"scores": {}, "total_score": 9.0, "passed": True, "feedback": "x"},
            }
        ]
    )
    wrong_payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    assert_case_run_state(first_case_run(wrong_payload), EvaluationCaseRunState.ERROR)


@pytest.mark.asyncio
async def test_c8_multi_key_scores_are_prefixed(
    judge_harness: JudgeHarness,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    await seed_judge_tool(
        mock_llm_redis,
        scores={"a": 8.0, "b": 6.0},
        passed=True,
        feedback="multi",
    )
    payload = await run_case_and_wait(
        judge_harness.client,
        suite_id=judge_harness.suite.suite_id,
        case_id=judge_harness.case.case_id,
    )
    case_run = first_case_run(payload)
    assert_score_keys(
        case_run,
        {"turn_1.check_1.a": 8.0, "turn_1.check_1.b": 6.0},
    )
    assert case_run.total_score == 7.0


@pytest.mark.asyncio
async def test_c9_rubric_version_pin_is_immutable(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_rubric_pin_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"Pin suite {unique_id}")
        rubric = await create_rubric(
            client,
            flow_id,
            f"Pin rubric {unique_id}",
            pass_threshold=9.0,
        )
        v1_id = rubric.version.rubric_version_id
        _ = await create_rubric_version(
            client,
            rubric.rubric.rubric_id,
            prompt="Loose v2",
            pass_threshold=5.0,
        )
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Pin case {unique_id}",
            turns=[text_turn("ping", [judge_check(v1_id)])],
        )
        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 6.0},
            passed=None,
            feedback="still on v1",
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        # v1 threshold 9 → 6 fails; if v2 were used, 6 would pass
        assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.FAILED)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_c12_missing_rubric_version_rejected_on_create(
    client: AsyncClient,
    unique_id: str,
) -> None:
    flow_id = f"eval_missing_rubric_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Missing rubric suite {unique_id}")
        response = await client.post(
            f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
            json={
                "name": f"Bad rubric case {unique_id}",
                "branch_ids": "*",
                "turns": [
                    text_turn(
                        "ping",
                        [
                            {
                                "type": "llm_judge",
                                "rubric_version_id": "",
                                "judge_node_id": None,
                                "judge_node": None,
                            }
                        ],
                    )
                ],
            },
        )
        assert response.status_code >= 400, response.text
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_c13_missing_judge_node_errors_on_run(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_missing_judge_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Missing judge suite {unique_id}")
        rubric = await create_rubric(client, flow_id, f"Missing judge rubric {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Missing judge case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [judge_check(rubric.version.rubric_version_id, judge_node_id="does_not_exist")],
                )
            ],
        )
        await seed_judge_tool(mock_llm_redis, scores={"quality": 9.0}, passed=True)
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.ERROR)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_c14_legacy_default_judge_without_node_id(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_legacy_judge_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Legacy judge suite {unique_id}")
        rubric = await create_rubric(client, flow_id, f"Legacy judge rubric {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Legacy judge case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [judge_check(rubric.version.rubric_version_id, judge_node_id=None)],
                )
            ],
        )
        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 9.0},
            passed=True,
            feedback="legacy ok",
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.judge_feedback == "legacy ok"
        assert EVALUATION_JUDGE_TOOL_NAME == "record_evaluation_judgment"
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_judge_with_contains_still_runs_flow_first(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    """Regression: deterministic check + judge on same turn."""
    flow_id = f"eval_mixed_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"Mixed suite {unique_id}")
        rubric = await create_rubric(client, flow_id, f"Mixed rubric {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Mixed case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [
                        contains_check("Echo"),
                        judge_check(rubric.version.rubric_version_id),
                    ],
                )
            ],
        )
        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 9.0},
            passed=True,
            feedback="after contains",
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.scores is not None
        assert "turn_1.check_1.result" in case_run.scores
        assert "turn_1.check_2.quality" in case_run.scores
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
