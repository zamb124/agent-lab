"""Runs surface gaps: trials, scope, matrix scores, events-page, pairwise after judge."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from apps.flows.src.evaluation.lab_service import (
    EVALUATION_JUDGE_TOOL_NAME,
    EVALUATION_PAIRWISE_TOOL_NAME,
)
from apps.flows.src.models.evaluation_lab import (
    EvaluationCaseRunState,
    EvaluationPairwiseJudgment,
    EvaluationPairwisePreference,
    EvaluationResultsMatrix,
    EvaluationRunEventsPage,
    EvaluationRunState,
)
from core.clients.llm.mock import MockLLMQueuedResponse
from core.pagination import ListResponse
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    contains_check,
    create_case,
    create_echo_flow,
    create_rubric,
    create_run,
    create_suite,
    ensure_judge_and_tester_nodes,
    first_case_run,
    judge_check,
    run_case_and_wait,
    seed_judge_tool,
    text_turn,
    wait_for_run,
)


@pytest.mark.asyncio
async def test_trials_create_three_case_runs(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_trials_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Trials suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Trials case {unique_id}",
            turns=[text_turn("ping", [contains_check("Echo")])],
        )
        created = await create_run(
            client,
            suite_id=suite.suite_id,
            case_ids=[case.case_id],
            trials=3,
        )
        payload = await wait_for_run(client, created.run.run_id)
        assert payload.run.state == EvaluationRunState.PASSED
        assert len(payload.case_runs) == 3
        trial_indexes = sorted(item.trial_index for item in payload.case_runs)
        assert trial_indexes == [1, 2, 3]
        assert all(item.state == EvaluationCaseRunState.PASSED for item in payload.case_runs)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_scope_suite_vs_cases(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_scope_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Scope suite {unique_id}")
        case_a = await create_case(
            client,
            suite.suite_id,
            name=f"Scope A {unique_id}",
            turns=[text_turn("a", [contains_check("Echo")])],
        )
        case_b = await create_case(
            client,
            suite.suite_id,
            name=f"Scope B {unique_id}",
            turns=[text_turn("b", [contains_check("Echo")])],
        )

        suite_run = await create_run(client, suite_id=suite.suite_id, case_ids=None)
        suite_payload = await wait_for_run(client, suite_run.run.run_id)
        assert len(suite_payload.case_runs) == 2

        cases_run = await create_run(
            client,
            suite_id=suite.suite_id,
            case_ids=[case_a.case_id],
        )
        cases_payload = await wait_for_run(client, cases_run.run.run_id)
        assert len(cases_payload.case_runs) == 1
        assert cases_payload.case_runs[0].case_id == case_a.case_id
        assert case_b.case_id not in {item.case_id for item in cases_payload.case_runs}
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_matrix_cell_has_score_after_judge(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_matrix_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"Matrix suite {unique_id}")
        rubric = await create_rubric(client, flow_id, f"Matrix rubric {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Matrix case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [judge_check(rubric.version.rubric_version_id)],
                )
            ],
        )
        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 8.5},
            passed=True,
            feedback="matrix ok",
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)

        matrix_response = await client.get(
            f"/flows/api/v1/evaluation/suites/{suite.suite_id}/matrix",
            params={"branch_id": "default"},
        )
        assert matrix_response.status_code == 200, matrix_response.text
        matrix = EvaluationResultsMatrix.model_validate(matrix_response.json())
        matching_cells = [
            cell
            for cell in matrix.cells
            if cell.case_id == case.case_id and cell.case_run_id == case_run.case_run_id
        ]
        assert len(matching_cells) >= 1
        cell = matching_cells[0]
        assert cell.case_run_id == case_run.case_run_id
        assert cell.total_score == 8.5
        assert cell.state == EvaluationCaseRunState.PASSED
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_events_page_cursor_after_multi_check(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_events_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Events suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Events case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [
                        contains_check("Echo"),
                        contains_check("answer=42"),
                        contains_check("42"),
                    ],
                )
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert payload.run.state == EvaluationRunState.PASSED

        first_page_response = await client.get(
            f"/flows/api/v1/evaluation/runs/{payload.run.run_id}/events-page",
            params={"limit": 3},
        )
        assert first_page_response.status_code == 200, first_page_response.text
        first_page = EvaluationRunEventsPage.model_validate(first_page_response.json())
        assert len(first_page.items) == 3
        assert first_page.has_more is True
        assert first_page.next_sequence is not None

        next_page_response = await client.get(
            f"/flows/api/v1/evaluation/runs/{payload.run.run_id}/events-page",
            params={"after_sequence": first_page.next_sequence, "limit": 100},
        )
        assert next_page_response.status_code == 200, next_page_response.text
        next_page = EvaluationRunEventsPage.model_validate(next_page_response.json())
        assert len(next_page.items) >= 1
        first_ids = {item.event_id for item in first_page.items}
        next_ids = {item.event_id for item in next_page.items}
        assert first_ids.isdisjoint(next_ids)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_pairwise_after_two_judge_runs(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_pairwise_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"Pairwise suite {unique_id}")
        rubric = await create_rubric(
            client,
            flow_id,
            f"Pairwise rubric {unique_id}",
            prompt="Prefer clearer feedback.",
        )
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Pairwise case {unique_id}",
            turns=[text_turn("ping", [judge_check(rubric.version.rubric_version_id)])],
        )

        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 7.0},
            passed=True,
            feedback="left feedback",
        )
        left_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=case.case_id
        )
        left = first_case_run(left_payload)

        await seed_judge_tool(
            mock_llm_redis,
            scores={"quality": 9.0},
            passed=True,
            feedback="right feedback stronger",
        )
        right_payload = await run_case_and_wait(
            client, suite_id=suite.suite_id, case_id=case.case_id
        )
        right = first_case_run(right_payload)

        await mock_llm_redis(
            [
                {
                    "type": "tool_call",
                    "tool": EVALUATION_PAIRWISE_TOOL_NAME,
                    "args": {
                        "preferred": "right",
                        "scores": {"delta": 2.0},
                        "feedback": "right has stronger quality",
                    },
                }
            ]
        )
        pairwise_response = await client.post(
            "/flows/api/v1/evaluation/pairwise-judgments",
            json={
                "left_case_run_id": left.case_run_id,
                "right_case_run_id": right.case_run_id,
                "mode": "llm",
                "rubric_version_id": rubric.version.rubric_version_id,
            },
        )
        assert pairwise_response.status_code == 200, pairwise_response.text
        judgment = EvaluationPairwiseJudgment.model_validate(pairwise_response.json())
        assert judgment.preferred == EvaluationPairwisePreference.RIGHT
        assert judgment.feedback == "right has stronger quality"

        list_response = await client.get(
            f"/flows/api/v1/evaluation/case-runs/{right.case_run_id}/pairwise-judgments"
        )
        assert list_response.status_code == 200, list_response.text
        listed = ListResponse[EvaluationPairwiseJudgment].model_validate(list_response.json())
        assert judgment.pairwise_judgment_id in {
            item.pairwise_judgment_id for item in listed.items
        }
        assert EVALUATION_JUDGE_TOOL_NAME
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
