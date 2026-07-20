"""Input kinds matrix — text / inline_code / node through full evaluation runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from apps.flows.src.models.evaluation_lab import EvaluationCaseRunState, EvaluationRunState
from core.clients.llm.mock import MockLLMQueuedResponse
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    assert_case_stores_ids_only,
    assert_score_keys,
    contains_check,
    create_case,
    create_echo_flow,
    create_suite,
    ensure_judge_and_tester_nodes,
    first_case_run,
    get_case,
    inline_code_turn,
    node_input_turn,
    put_flow_nodes,
    run_case_and_wait,
    text_turn,
)


@pytest.mark.asyncio
async def test_a1_text_input_contains_pass(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_a1_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"A1 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A1 case {unique_id}",
            turns=[text_turn("hello-matrix", [contains_check("Echo: hello-matrix")])],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert payload.run.state == EvaluationRunState.PASSED
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.dialog[0].content == "hello-matrix"
        assert_score_keys(case_run, {"turn_1.check_1.result": 10.0})
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a2_inline_code_python(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_a2_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"A2 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A2 case {unique_id}",
            turns=[
                inline_code_turn(
                    "async def run(args, state):\n    return 'inline-python-42'\n",
                    [contains_check("inline-python-42")],
                    language="python",
                )
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert "inline-python-42" in case_run.dialog[0].content
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a3_inline_code_javascript(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_a3_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"A3 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A3 case {unique_id}",
            turns=[
                inline_code_turn(
                    "async function run(args, state) {\n  return 'inline-js-99';\n}\n",
                    [contains_check("inline-js-99")],
                    language="javascript",
                )
            ],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert "inline-js-99" in case_run.dialog[0].content
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a4_node_tester_persists_id_only(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_a4_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(client, flow_id)
        suite = await create_suite(client, flow_id, f"A4 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A4 case {unique_id}",
            turns=[
                node_input_turn(
                    [contains_check("Echo")],
                    node_id="eval_tester",
                )
            ],
        )
        assert_case_stores_ids_only(case)
        await mock_llm_redis([{"type": "text", "content": "tester says ping"}])
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.dialog[0].content == "tester says ping"
        loaded = await get_case(client, suite.suite_id, case.case_id)
        assert loaded.turns[0].input.type == "node"
        assert loaded.turns[0].input.node_id == "eval_tester"
        assert loaded.turns[0].input.node is None
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a5_node_missing_node_id_errors(client: AsyncClient, unique_id: str) -> None:
    flow_id = f"eval_a5_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"A5 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A5 case {unique_id}",
            turns=[node_input_turn([contains_check("Echo")], node_id=None, node=None)],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.ERROR)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a6_node_id_preferred_over_legacy_inline_node(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_a6_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await ensure_judge_and_tester_nodes(
            client,
            flow_id,
            tester_prompt="Prefer flow tester node.",
        )
        suite = await create_suite(client, flow_id, f"A6 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A6 case {unique_id}",
            turns=[
                node_input_turn(
                    [contains_check("Echo")],
                    node_id="eval_tester",
                    node={
                        "type": "llm_node",
                        "prompt": "This inline node must not win.",
                    },
                )
            ],
        )
        await mock_llm_redis([{"type": "text", "content": "from-flow-tester"}])
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.dialog[0].content == "from-flow-tester"
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_a7_tester_node_with_llm_records_billing(
    client: AsyncClient,
    unique_id: str,
    mock_llm_redis: Callable[[list[MockLLMQueuedResponse]], Awaitable[None]],
) -> None:
    flow_id = f"eval_a7_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await put_flow_nodes(
            client,
            flow_id,
            extra_nodes={
                "eval_tester": {
                    "type": "llm_node",
                    "name": "Billed Tester",
                    "prompt": "Generate one short user message.",
                    "store": {"evaluation_role": "tester"},
                    "llm": {"temperature": 0.0},
                }
            },
        )
        suite = await create_suite(client, flow_id, f"A7 suite {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"A7 case {unique_id}",
            turns=[
                node_input_turn(
                    [contains_check("Echo")],
                    node_id="eval_tester",
                )
            ],
        )
        await mock_llm_redis([{"type": "text", "content": "billed ping"}])
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        case_run = first_case_run(payload)
        assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
        assert case_run.billing_quantity >= 1
        assert payload.run.billing_quantity >= 1
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
