"""Multi-turn dialog and score key naming."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx2 import AsyncClient

from apps.flows.src.models.evaluation_lab import EvaluationCaseRunState, EvaluationRunState
from core.clients.llm.mock import MockLLMQueuedResponse
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    assert_score_keys,
    contains_check,
    create_case,
    create_echo_flow,
    create_suite,
    ensure_judge_and_tester_nodes,
    first_case_run,
    length_check,
    node_input_turn,
    run_case_and_wait,
    text_turn,
)


@pytest.mark.asyncio
async def test_d1_two_text_turns_score_prefixes(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_d1_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"D1 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"D1 case {unique_id}",
            turns=[
                text_turn("first", [contains_check("Echo: first")]),
                text_turn("second", [contains_check("Echo: second")]),
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert len(case_run.dialog) >= 4
        assert_score_keys(
            case_run,
            {"turn_1.check_1.result": 10.0, "turn_2.check_1.result": 10.0},
        )
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_d2_turn1_text_turn2_tester_sees_prior_dialog(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_d2_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"D2 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"D2 case {unique_id}",
            turns=[
                text_turn("seed-turn", [contains_check("Echo: seed-turn")]),
                node_input_turn(
                    [contains_check("Echo")],
                    node_id="eval_tester",
                ),
            ],
        )
        await mock_llm_redis([{"type": "text", "content": "follow-up-from-tester"}])
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.dialog[0].content == "seed-turn"
        assert case_run.dialog[2].content == "follow-up-from-tester"
        assert case_run.dialog[2].content != case_run.dialog[0].content
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_d3_two_checks_on_one_turn_fail_one(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_d3_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"D3 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"D3 case {unique_id}",
            turns=[
                text_turn(
                    "ping",
                    [
                        contains_check("Echo"),
                        length_check(min_chars=10_000),
                    ],
                )
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.FAILED)
        assert case_run.scores is not None
        assert "turn_1.check_1.result" in case_run.scores
        assert "turn_1.check_2.result" in case_run.scores
        assert case_run.scores["turn_1.check_1.result"] == 10.0
        assert case_run.scores["turn_1.check_2.result"] == 0.0
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_d4_mid_turn_check_fail_stops_case(client: AsyncClient, unique_id: str) -> None:
    """As-is behavior: first failing check finishes the case_run as FAILED (no later turns)."""
    flow_id = f"eval_d4_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"D4 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"D4 case {unique_id}",
            turns=[
                text_turn("alpha", [contains_check("DOES-NOT-EXIST")]),
                text_turn("beta", [contains_check("Echo: beta")]),
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.FAILED)
        assert case_run.scores is not None
        assert "turn_1.check_1.result" in case_run.scores
        assert "turn_2.check_1.result" not in case_run.scores
        assert case_run.error is not None
        assert "Turn 1 check 1 failed" in case_run.error
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_d5_max_turns_exhausted_errors(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_d5_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"D5 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"D5 case {unique_id}",
            max_turns=1,
            turns=[
                text_turn("one", [contains_check("Echo")]),
                text_turn("two", [contains_check("Echo")]),
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert payload.run.state == EvaluationRunState.ERROR
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.ERROR)
        assert case_run.error is not None
        assert "max_turns=1" in case_run.error
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
