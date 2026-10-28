from __future__ import annotations

import pytest

from apps.flows.src.models import BranchConfig, Edge, FlowConfig

pytestmark = [pytest.mark.no_test_doubles]


def _child_flow(flow_id: str) -> FlowConfig:
    return FlowConfig(
        flow_id=flow_id,
        name="Профильный консультант",
        entry="done",
        nodes={"done": {"type": "channel", "channel": "email", "action": "send"}},
        edges=[Edge(from_node="done", to_node=None)],
        branches={
            "vip": BranchConfig(name="VIP", entry="done", nodes={}, edges=[]),
        },
    )


@pytest.mark.asyncio
async def test_create_flow_persists_typed_handoff_on_exact_tool_attachment(
    client,
    di,
    auth_headers_system,
    unique_id: str,
) -> None:
    child_flow_id = f"api-child-{unique_id}"
    parent_flow_id = f"api-parent-{unique_id}"
    await FlowConfig.create_version(_child_flow(child_flow_id))

    response = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": parent_flow_id,
            "name": "Маршрутизатор",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Передавай профильные вопросы консультанту",
                    "tools": [
                        {
                            "tool_id": "coach",
                            "type": "flow",
                            "flow_id": child_flow_id,
                            "branch_id": "vip",
                            "call_type": "handoff",
                        }
                    ],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )

    assert response.status_code == 200, response.text
    stored = await FlowConfig.current_for_flow(parent_flow_id)
    assert stored is not None
    assert stored.nodes is not None
    assert "call_type" not in stored.nodes["main"]
    tool = stored.nodes["main"]["tools"][0]
    assert tool["tool_id"] == "coach"
    assert tool["type"] == "flow"
    assert tool["flow_id"] == child_flow_id
    assert tool["branch_id"] == "vip"
    assert tool["call_type"] == "handoff"
    assert tool["parameters_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_create_flow_rejects_flow_tool_without_flow_id(
    client,
    auth_headers_system,
    unique_id: str,
) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": f"api-invalid-parent-{unique_id}",
            "name": "Invalid",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "tools": [
                        {
                            "tool_id": "coach",
                            "type": "flow",
                            "call_type": "handoff",
                        }
                    ],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_flow_rejects_unknown_target_branch(
    client,
    di,
    auth_headers_system,
    unique_id: str,
) -> None:
    child_flow_id = f"api-branch-child-{unique_id}"
    await FlowConfig.create_version(_child_flow(child_flow_id))

    response = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": f"api-branch-parent-{unique_id}",
            "name": "Invalid branch",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "tools": [
                        {
                            "tool_id": "coach",
                            "type": "flow",
                            "flow_id": child_flow_id,
                            "branch_id": "missing",
                            "call_type": "handoff",
                        }
                    ],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )

    assert response.status_code == 400
    assert "has no branch 'missing'" in response.json()["detail"]
