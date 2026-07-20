"""Deterministic EvaluationCheck types — pass and fail per discriminator."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.flows.src.models.evaluation_lab import EvaluationCaseRunState, EvaluationRunWithCases
from tests.flows.e2e.evaluation.helpers import (
    assert_case_run_state,
    assert_score_keys,
    code_check,
    contains_check,
    create_case,
    create_echo_flow,
    create_suite,
    first_case_run,
    json_schema_check,
    length_check,
    not_contains_check,
    regex_check,
    run_case_and_wait,
    state_path_check,
    text_turn,
    trace_assertion_check,
)


async def _run_text_case(
    client: AsyncClient,
    unique_id: str,
    *,
    suffix: str,
    content: str,
    checks: list[dict[str, object]],
) -> EvaluationRunWithCases:
    flow_id = f"eval_det_{suffix}_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Det {suffix} {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Det {suffix} case {unique_id}",
            turns=[text_turn(content, checks)],
        )
        return await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_contains_pass_and_fail(client: AsyncClient, unique_id: str) -> None:
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="contains_pass",
        content="ping",
        checks=[contains_check("Echo", mode="any")],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="contains_fail",
        content="ping",
        checks=[contains_check("MISSING", "ALSO", mode="all")],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_contains_case_sensitive(client: AsyncClient, unique_id: str) -> None:
    failed = await _run_text_case(
        client,
        unique_id,
        suffix="contains_cs",
        content="ping",
        checks=[contains_check("echo", case_sensitive=True)],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_not_contains_pass_and_fail(client: AsyncClient, unique_id: str) -> None:
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="not_contains_pass",
        content="ping",
        checks=[not_contains_check("fatal")],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="not_contains_fail",
        content="ping",
        checks=[not_contains_check("Echo")],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_regex_pass_and_fail(client: AsyncClient, unique_id: str) -> None:
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="regex_pass",
        content="ping",
        checks=[regex_check(r"Echo:.*answer=42")],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="regex_fail",
        content="ping",
        checks=[regex_check(r"^NOPE$")],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_length_min_max_and_invalid(client: AsyncClient, unique_id: str) -> None:
    passed_min = await _run_text_case(
        client,
        unique_id,
        suffix="len_min",
        content="ping",
        checks=[length_check(min_chars=1)],
    )
    assert_case_run_state(first_case_run(passed_min), EvaluationCaseRunState.PASSED)

    passed_max = await _run_text_case(
        client,
        unique_id,
        suffix="len_max",
        content="ping",
        checks=[length_check(max_chars=10_000)],
    )
    assert_case_run_state(first_case_run(passed_max), EvaluationCaseRunState.PASSED)

    passed_both = await _run_text_case(
        client,
        unique_id,
        suffix="len_both",
        content="ping",
        checks=[length_check(min_chars=1, max_chars=10_000)],
    )
    assert_case_run_state(first_case_run(passed_both), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="len_fail",
        content="ping",
        checks=[length_check(max_chars=1)],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)

    flow_id = f"eval_det_len_invalid_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        suite = await create_suite(client, flow_id, f"Len invalid {unique_id}")
        case = await create_case(
            client,
            suite.suite_id,
            name=f"Len invalid case {unique_id}",
            turns=[text_turn("ping", [length_check()])],
        )
        payload = await run_case_and_wait(client, suite_id=suite.suite_id, case_id=case.case_id)
        assert_case_run_state(first_case_run(payload), EvaluationCaseRunState.ERROR)
    finally:
        _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_state_path_operators(client: AsyncClient, unique_id: str) -> None:
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="state_pass",
        content="ping",
        checks=[
            state_path_check("answer", "eq", "42"),
            state_path_check("structured_output.ok", "eq", True),
            state_path_check("structured_output.answer", "exists"),
        ],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="state_fail",
        content="ping",
        checks=[state_path_check("answer", "eq", "nope")],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_json_schema_valid_and_invalid(client: AsyncClient, unique_id: str) -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"const": "42"}, "ok": {"const": True}},
        "required": ["answer", "ok"],
    }
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="schema_pass",
        content="ping",
        checks=[json_schema_check(schema)],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    bad_schema = {
        "type": "object",
        "required": ["missing_field"],
    }
    failed = await _run_text_case(
        client,
        unique_id,
        suffix="schema_fail",
        content="ping",
        checks=[json_schema_check(bad_schema)],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_trace_assertion_node_completed(client: AsyncClient, unique_id: str) -> None:
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="trace_pass",
        content="ping",
        checks=[trace_assertion_check("node_completed", "echo")],
    )
    assert_case_run_state(first_case_run(passed), EvaluationCaseRunState.PASSED)

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="trace_fail",
        content="ping",
        checks=[trace_assertion_check("node_completed", "missing_node")],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_code_check_python_pass_and_fail(client: AsyncClient, unique_id: str) -> None:
    pass_source = (
        "async def run(args, state):\n"
        "    return {'semantic': 9.0, 'gate': 'Echo' in args['response']}\n"
    )
    fail_source = (
        "async def run(args, state):\n"
        "    return {'semantic': 1.0, 'gate': False}\n"
    )
    passed = await _run_text_case(
        client,
        unique_id,
        suffix="code_pass",
        content="ping",
        checks=[code_check(pass_source)],
    )
    case_run = first_case_run(passed)
    assert_case_run_state(case_run, EvaluationCaseRunState.PASSED)
    assert case_run.scores is not None
    assert "turn_1.check_1.semantic" in case_run.scores

    failed = await _run_text_case(
        client,
        unique_id,
        suffix="code_fail",
        content="ping",
        checks=[code_check(fail_source)],
    )
    assert_case_run_state(first_case_run(failed), EvaluationCaseRunState.FAILED)


@pytest.mark.asyncio
async def test_score_recorded_keys_for_contains(client: AsyncClient, unique_id: str) -> None:
    payload = await _run_text_case(
        client,
        unique_id,
        suffix="score_keys",
        content="ping",
        checks=[contains_check("Echo")],
    )
    assert_score_keys(first_case_run(payload), {"turn_1.check_1.result": 10.0})
