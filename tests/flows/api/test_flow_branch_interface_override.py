"""PUT flow сохраняет BranchConfig.interface_override (replace) end-to-end."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.flows.src.api.v1.flows import FlowResponse
from core.models.flow_interface import default_flow_interface_config


@pytest.mark.asyncio
async def test_put_flow_persists_branch_interface_override(
    client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"branch_iface_{unique_id}"
    branch_id = f"brant_{unique_id}"
    code = "async def run(args, state):\n    return state"
    replacement = default_flow_interface_config().model_dump(mode="json")
    replacement["template"]["document"]["surfaces"]["main"]["data_model"]["content"][
        "greeting"
    ] = f"branch-hello-{unique_id}"

    create_resp = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Branch interface override",
            "entry": "main",
            "nodes": {"main": {"type": "code", "code": code}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    put_resp = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Branch interface override",
            "entry": "main",
            "nodes": {"main": {"type": "code", "code": code}},
            "edges": [{"from_node": "main", "to_node": None}],
            "branches": {
                branch_id: {
                    "name": branch_id,
                    "description": "branch with replace interface",
                    "entry": "main",
                    "nodes": {},
                    "edges": [],
                    "nodes_mode": "replace",
                    "edges_mode": "replace",
                    "interface_override": {
                        "mode": "replace",
                        "replacement": replacement,
                    },
                }
            },
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    put_flow = FlowResponse.model_validate(put_resp.json())
    put_override = put_flow.branches[branch_id].interface_override
    assert put_override.mode == "replace"
    assert put_override.replacement is not None
    assert (
        put_override.replacement.template.document.surfaces["main"].data_model.content[
            "greeting"
        ]
        == f"branch-hello-{unique_id}"
    )

    get_resp = await client.get(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert get_resp.status_code == 200, get_resp.text
    get_flow = FlowResponse.model_validate(get_resp.json())
    get_override = get_flow.branches[branch_id].interface_override
    assert get_override.mode == "replace"
    assert get_override.replacement is not None
    assert (
        get_override.replacement.template.document.surfaces["main"].data_model.content[
            "greeting"
        ]
        == f"branch-hello-{unique_id}"
    )

    delete_resp = await client.delete(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
    )
    assert delete_resp.status_code in {200, 204}, delete_resp.text
