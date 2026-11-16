"""GET /flows/api/v1/schema отдаёт JSON Schema тех же моделей, что принимает запись flow."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_flow_contract_schema_lists_create_and_evaluation(client) -> None:
    response = await client.get("/flows/api/v1/schema")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["flow_create"]["title"] == "FlowCreateRequest"
    assert "base_version" in body["flow_create"]["properties"]
    assert body["evaluation_case"]["title"] == "EvaluationCaseCreateRequest"
    assert "oneOf" in body["evaluation_check"] or "anyOf" in body["evaluation_check"]
    assert body["graph_node"]["title"] == "GraphNodeConfig"
