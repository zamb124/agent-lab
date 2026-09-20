"""Prod-like dataflow inspect: REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.realtime.operations import FlowDataflowInspectRequest, op_flows_dataflow_inspect
from apps.flows.src.container import FlowContainer
from apps.flows.src.models import DataflowInspectResult
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_dataflow_inspect_inline_payload(client: AsyncClient, unique_id: str) -> None:
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
    data = DataflowInspectResult.model_validate(response.json())
    assert data.nodes["llm_1"].node_type == "llm_node"


async def test_dataflow_inspect_flow_id_from_db(client: AsyncClient, unique_id: str) -> None:
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
    data = DataflowInspectResult.model_validate(response.json())
    assert data.flow_id == flow_id
    assert "main" in data.nodes
    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_dataflow_inspect_unknown_flow_id_403(client: AsyncClient, unique_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        json={"flow_id": f"missing_{unique_id}", "branch_id": "default"},
    )
    assert response.status_code == 403


async def test_dataflow_inspect_malformed_node_type_422(client: AsyncClient) -> None:
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


async def test_dataflow_inspect_graph_issues_entry_not_found(client: AsyncClient) -> None:
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
    data = DataflowInspectResult.model_validate(response.json())
    assert any(issue.code == "entry_not_found" for issue in data.issues)


async def test_dataflow_inspect_entry_canvas_realistic_inputs(
    client: AsyncClient, unique_id: str
) -> None:
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
    data = DataflowInspectResult.model_validate(response.json())
    labels = {chip.label for chip in data.nodes["llm_1"].canvas.inputs}
    assert "content" in labels
    assert "variables.company_name" in labels
    assert "triggers.tg_1.context.chat_id" in labels
    assert "breakpoint_state" not in labels
    assert "node_history" not in labels


async def test_dataflow_inspect_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"inspect_cmd_{unique_id}"
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Inspect Command",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "{topic}"}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert created.status_code == 200, created.text
    payload = FlowDataflowInspectRequest(flow_id=flow_id, branch_id="default")
    http_res = await client.post(
        "/flows/api/v1/flows/dataflow/inspect",
        headers=auth_headers_system,
        json=payload.model_dump(mode="json"),
    )
    assert http_res.status_code == 200, http_res.text
    with _system_scope(system_user_id) as user:
        op_res = await op_flows_dataflow_inspect(
            payload,
            user=user,
            container=container,
        )
    assert op_res.model_dump(mode="json") == http_res.json()
