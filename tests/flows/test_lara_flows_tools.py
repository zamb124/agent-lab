from __future__ import annotations

import json

import pytest
import pytest_asyncio

from apps.flows.tools.flows.flows_editor_tools import (
    flows_get_node,
    flows_list_nodes,
    flows_patch_flow,
    flows_patch_node,
    flows_read_context,
)
from core.flow_ui.document import FlowUIActionPreview, FlowUIActionResult, FlowUIButton
from core.state import ExecutionState
from tests.flows._flow_ui import conversation_block, conversation_blocks

pytestmark = [pytest.mark.timeout(90, func_only=True)]


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
        "edges": [{"from_node": "main", "to_node": None}],
        "variables": {},
        "tags": ["test", "lara"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }
    response = await flows_client.post(
        "/flows/api/v1/flows/", json=payload, headers=auth_headers_system
    )
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
        {"flow_id": flow_id, "branch_id": "base", "node_id": "main"}, state
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_id"] == flow_id
    assert data["branch_id"] == "base"
    assert data["node_id"] == "main"
    assert data["node"]["prompt"] == "Initial prompt"
    assert "nodes" not in data["flow"]
    assert "edges" not in data["flow"]
    assert data["flow"]["entry"] == "main"
    assert "variables_keys" in data["flow"]
    assert isinstance(data["nodes_index"], list)
    assert any(item["node_id"] == "main" for item in data["nodes_index"])
    for item in data["nodes_index"]:
        assert "prompt" not in item
        assert "code" not in item


@pytest.mark.asyncio
async def test_flows_get_node_returns_single_node_without_graph(
    flows_service,
    flows_client,
    auth_headers_system,
    lara_flows_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    flow_id = await _create_test_flow(flows_client, unique_id, auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    raw = await flows_get_node._run_impl(
        {"flow_id": flow_id, "branch_id": "base", "node_id": "main"}, state
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_id"] == flow_id
    assert data["branch_id"] == "base"
    assert data["node_id"] == "main"
    assert data["node"]["prompt"] == "Initial prompt"
    assert "flow" not in data
    assert "nodes_index" not in data


@pytest.mark.asyncio
async def test_flows_list_nodes_returns_index_without_prompt_bodies(
    flows_service,
    flows_client,
    auth_headers_system,
    lara_flows_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    flow_id = await _create_test_flow(flows_client, unique_id, auth_headers_system)
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    raw = await flows_list_nodes._run_impl({"flow_id": flow_id, "branch_id": "base"}, state)
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_id"] == flow_id
    assert data["branch_id"] == "base"
    assert data["entry"] == "main"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node_id"] == "main"
    assert data["nodes"][0]["type"] == "llm_node"
    assert "prompt" not in data["nodes"][0]
    assert "ask_user" in data["nodes"][0]["tools"]


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
    preview = conversation_block(state, f"flows-node-preview-{pending_action_id}")
    assert isinstance(preview, FlowUIActionPreview)
    assert preview.parameters["changes"]["prompt"] == new_prompt
    apply_button = conversation_block(state, f"flows-node-preview-{pending_action_id}-apply")
    assert isinstance(apply_button, FlowUIButton)
    assert apply_button.action is not None
    assert apply_button.action.name == "apply_pending_action"
    assert apply_button.action.payload["pending_action_id"] == pending_action_id
    apply_raw = await flows_patch_node._run_impl(
        {"mode": "apply", "pending_action_id": pending_action_id}, state
    )
    data = json.loads(apply_raw)
    assert data["success"] is True
    assert data["node_after"]["prompt"] == new_prompt
    applied = conversation_blocks(state)[-1]
    assert isinstance(applied, FlowUIActionResult)
    assert applied.block_id == f"flows-node-apply-{pending_action_id}"
    assert applied.status == "success"
    flow_resp = await flows_client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
    )
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
        {"flow_id": flow_id, "patch_json": json.dumps({"name": proposed_name}), "mode": "propose"},
        state,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["flow_after"]["name"] == proposed_name
    assert isinstance(data.get("pending_action_id"), str) and data["pending_action_id"]
    preview = conversation_block(state, f"flows-flow-preview-{data['pending_action_id']}")
    assert isinstance(preview, FlowUIActionPreview)
    assert preview.parameters["flow_changes"]["name"] == proposed_name
    apply_button = conversation_block(
        state, f"flows-flow-preview-{data['pending_action_id']}-apply"
    )
    assert isinstance(apply_button, FlowUIButton)
    assert apply_button.action is not None
    assert apply_button.action.name == "apply_pending_action"
    assert apply_button.action.payload["pending_action_id"] == data["pending_action_id"]
    flow_resp = await flows_client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
    )
    assert flow_resp.status_code == 200, flow_resp.text
    assert flow_resp.json()["name"] != proposed_name
