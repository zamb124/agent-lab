"""HTTP contract tests for dataflow inspect endpoint."""

import pytest


@pytest.mark.asyncio
async def test_dataflow_inspect_inline_payload(client, app, unique_id):
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={
            "flow_id": f"inspect_{unique_id}",
            "branch_id": "default",
            "entry": "code_1",
            "nodes": {
                "code_1": {
                    "type": "code",
                    "language": "python",
                    "code": "async def run(a,s):\n    state.topic='x'\n    return {}",
                },
                "llm_1": {
                    "type": "llm_node",
                    "prompt": "{topic}",
                    "input_mapping": {"topic": "@state:topic"},
                },
            },
            "edges": [{"from_node": "code_1", "to_node": "llm_1"}],
            "variables": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "llm_1" in data["nodes"]
    llm = data["nodes"]["llm_1"]
    assert "canvas" in llm
    assert "required_inputs" in llm
    assert "issues" in llm
    assert "input_mapping" in llm


@pytest.mark.asyncio
async def test_dataflow_inspect_flow_id_from_db(client, app, unique_id):
    flow_id = f"inspect_db_{unique_id}"
    create = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Inspect DB",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "{topic}"}},
            "edges": [{"from_node": "main", "to_node": None}],
            "variables": {},
        },
    )
    assert create.status_code == 200
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={"flow_id": flow_id, "branch_id": "default"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["flow_id"] == flow_id
    assert "main" in data["nodes"]
    await client.delete(f"/flows/api/v1/flows/{flow_id}")


@pytest.mark.asyncio
async def test_dataflow_inspect_unknown_flow_id_403(client, app, unique_id):
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={"flow_id": f"missing_{unique_id}", "branch_id": "default"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dataflow_inspect_malformed_node_type_422(client, app):
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={
            "entry": "bad",
            "nodes": {"bad": {"type": "not_a_real_node_type"}},
            "edges": [],
            "variables": {},
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dataflow_inspect_graph_issues_entry_not_found(client, app):
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={
            "entry": "missing",
            "nodes": {"a": {"type": "llm_node", "prompt": "ok"}},
            "edges": [],
            "variables": {},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert any(issue["code"] == "entry_not_found" for issue in data["issues"])


@pytest.mark.asyncio
async def test_dataflow_inspect_entry_canvas_realistic_inputs(client, app, unique_id):
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={
            "flow_id": f"inspect_canvas_{unique_id}",
            "branch_id": "default",
            "entry": "llm_1",
            "nodes": {"llm_1": {"type": "llm_node", "prompt": "ok"}},
            "edges": [],
            "variables": {
                "company_name": {"value": "ACME"},
            },
            "triggers": {
                "tg_1": {
                    "trigger_id": "tg_1",
                    "name": "Telegram",
                    "type": "telegram",
                    "enabled": True,
                    "output_mapping": {
                        "content": "message.text",
                        "context.chat_id": "message.chat.id",
                    },
                },
            },
            "sample_state": {
                "content": "hello",
                "breakpoint_state": {"hit": True},
                "node_history": ["llm_1"],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    labels = {chip["label"] for chip in data["nodes"]["llm_1"]["canvas"]["inputs"]}
    assert "content" in labels
    assert "variables.company_name" in labels
    assert "triggers.tg_1.context.chat_id" in labels
    assert "breakpoint_state" not in labels
    assert "node_history" not in labels
