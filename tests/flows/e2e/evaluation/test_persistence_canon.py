"""Persistence canon: case stores ids only; judge/tester body lives in FlowConfig."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.flows.e2e.evaluation.helpers import (
    assert_case_stores_ids_only,
    contains_check,
    create_case,
    create_echo_flow,
    create_rubric,
    create_suite,
    ensure_judge_and_tester_nodes,
    get_case,
    json_object,
    judge_check,
    text_turn,
)


@pytest.mark.asyncio
async def test_case_persists_judge_and_tester_node_ids_only(
    client: AsyncClient,
    unique_id: str,
) -> None:
    flow_id = f"eval_persist_{unique_id}"
    await create_echo_flow(client, flow_id)
    await ensure_judge_and_tester_nodes(
        client,
        flow_id,
        judge_prompt="Persist judge prompt",
        tester_prompt="Persist tester prompt",
    )
    suite = await create_suite(client, flow_id, f"Persist suite {unique_id}")
    rubric = await create_rubric(client, flow_id, f"Persist rubric {unique_id}")
    created = await create_case(
        client,
        suite.suite_id,
        name=f"Persist case {unique_id}",
        turns=[
            {
                "input": {
                    "type": "node",
                    "node_id": "eval_tester",
                    "node": None,
                },
                "checks": [judge_check(rubric.version.rubric_version_id)],
            }
        ],
    )
    assert_case_stores_ids_only(created)

    loaded = await get_case(client, suite.suite_id, created.case_id)
    assert_case_stores_ids_only(loaded)
    assert loaded.turns[0].input.type == "node"
    assert loaded.turns[0].input.node_id == "eval_tester"
    assert loaded.turns[0].checks[0].type == "llm_judge"
    assert loaded.turns[0].checks[0].judge_node_id == "eval_judge"
    assert loaded.turns[0].checks[0].judge_node is None

    flow_response = await client.get(f"/flows/api/v1/flows/{flow_id}")
    assert flow_response.status_code == 200, flow_response.text
    flow = json_object(flow_response.json())
    nodes = json_object(flow.get("nodes"))
    judge = json_object(nodes.get("eval_judge"))
    tester = json_object(nodes.get("eval_tester"))
    assert judge.get("prompt") == "Persist judge prompt"
    assert tester.get("prompt") == "Persist tester prompt"
    assert json_object(judge.get("store")).get("evaluation_role") == "judge"
    assert json_object(tester.get("store")).get("evaluation_role") == "tester"

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_text_case_does_not_require_judge_nodes(
    client: AsyncClient,
    unique_id: str,
) -> None:
    flow_id = f"eval_persist_text_{unique_id}"
    await create_echo_flow(client, flow_id)
    suite = await create_suite(client, flow_id, f"Text suite {unique_id}")
    created = await create_case(
        client,
        suite.suite_id,
        name=f"Text case {unique_id}",
        turns=[text_turn("ping", [contains_check("Echo")])],
    )
    loaded = await get_case(client, suite.suite_id, created.case_id)
    assert loaded.turns[0].input.type == "text"
    assert loaded.turns[0].checks[0].type == "contains"
    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
