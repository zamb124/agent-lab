from __future__ import annotations

import json

import pytest
import pytest_asyncio

from apps.flows.tools.lara_crm import flows_patch_flow, flows_patch_node, flows_read_context
from core.state import ExecutionState

pytestmark = [
    pytest.mark.timeout(90, func_only=True),
]


@pytest_asyncio.fixture
async def lara_flows_tool_context(auth_token_system, system_user_id):
    from core.context import set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    ctx = Context(
        user=User(user_id=system_user_id, name="Lara Flows tools"),
        active_company=Company(company_id="system", name="System"),
        auth_token=auth_token_system,
        channel="test",
        active_namespace="default",
        metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
    )
    set_context(ctx)
    return ctx


def _tool_state(*, unique_id: str, system_user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"lara-flows-tool-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id=system_user_id,
        session_id=f"lara-flows:ctx-{unique_id}",
    )


async def _create_test_flow(flows_client, unique_id: str, auth_headers_system: dict) -> str:
    flow_id = f"lara_flows_tool_{unique_id}"
    payload = {
        "flow_id": flow_id,
        "name": f"Lara Flows Tool {unique_id}",
        "description": "Flow for Lara flows tools tests",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "name": "Main",
                "prompt": "Initial prompt",
                "tools": ["ask_user"],
            }
        },
        "edges": [{"from": "main", "to": None}],
        "variables": {},
        "tags": ["test", "lara"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }
    response = await flows_client.post("/flows/api/v1/flows/", json=payload, headers=auth_headers_system)
    assert response.status_code == 200, response.text
    return flow_id


@pytest.mark.asyncio
async def test_flows_read_context_returns_selected_node(
    flows_service,
    flows_client,
    auth_headers_system,
    lara_flows_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    flow_id = await _create_test_flow(flows_client, unique_id, auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)

    raw = await flows_read_context._run_impl(
        {"flow_id": flow_id, "branch_id": "base", "node_id": "main"},
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_id"] == flow_id
    assert data["branch_id"] == "base"
    assert data["node_id"] == "main"
    assert data["node"]["prompt"] == "Initial prompt"


@pytest.mark.asyncio
async def test_flows_patch_node_confirm_first_apply_persists_flow(
    flows_service,
    flows_client,
    auth_headers_system,
    lara_flows_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    flow_id = await _create_test_flow(flows_client, unique_id, auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    new_prompt = f"Updated prompt {unique_id}"

    propose_raw = await flows_patch_node._run_impl(
        {
            "flow_id": flow_id,
            "branch_id": "base",
            "node_id": "main",
            "patch_json": json.dumps({"prompt": new_prompt}),
            "mode": "propose",
        },
        state,
    )
    proposed = json.loads(propose_raw)
    pending_action_id = proposed["pending_action_id"]
    assert proposed["success"] is True
    pending_events = getattr(state, "ui_events_pending")
    assert pending_events[0]["type"] == "action_previewed"
    assert pending_events[0]["payload"]["changes"]["prompt"] == new_prompt
    preview_buttons = pending_events[0]["payload"]["blocks"][1]["buttons"]
    assert preview_buttons[0]["action_kind"] == "apply"
    assert preview_buttons[0]["action_id"] == "flows.node.patch.apply"

    apply_raw = await flows_patch_node._run_impl(
        {
            "flow_id": flow_id,
            "branch_id": "base",
            "node_id": "main",
            "patch_json": json.dumps({"prompt": new_prompt}),
            "mode": "apply",
            "pending_action_id": pending_action_id,
        },
        state,
    )
    data = json.loads(apply_raw)
    assert data["success"] is True
    assert data["node_after"]["prompt"] == new_prompt
    pending_events = getattr(state, "ui_events_pending")
    assert pending_events[-1]["type"] == "action_applied"
    assert pending_events[-1]["payload"]["changes"]["prompt"] == new_prompt

    flow_resp = await flows_client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
    assert flow_resp.status_code == 200, flow_resp.text
    assert flow_resp.json()["nodes"]["main"]["prompt"] == new_prompt


@pytest.mark.asyncio
async def test_flows_patch_flow_propose_does_not_persist(
    flows_service,
    flows_client,
    auth_headers_system,
    lara_flows_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    flow_id = await _create_test_flow(flows_client, unique_id, auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    proposed_name = f"Proposed {unique_id}"

    raw = await flows_patch_flow._run_impl(
        {
            "flow_id": flow_id,
            "patch_json": json.dumps({"name": proposed_name}),
            "mode": "propose",
        },
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_after"]["name"] == proposed_name
    assert isinstance(data.get("pending_action_id"), str) and data["pending_action_id"]
    pending_events = getattr(state, "ui_events_pending")
    assert pending_events[0]["type"] == "action_previewed"
    assert pending_events[0]["payload"]["flow_changes"]["name"] == proposed_name
    preview_buttons = pending_events[0]["payload"]["blocks"][1]["buttons"]
    assert preview_buttons[0]["action_kind"] == "apply"
    assert preview_buttons[0]["action_id"] == "flows.flow.patch.apply"

    flow_resp = await flows_client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
    assert flow_resp.status_code == 200, flow_resp.text
    assert flow_resp.json()["name"] != proposed_name
