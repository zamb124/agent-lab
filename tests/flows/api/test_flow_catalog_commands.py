"""Prod-like каталог flow: REST и `op_*` — один handler, один JSON."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.operations import (
    FlowsFlowIdPayload,
    FlowsListPayload,
    op_flows_item,
    op_flows_list,
    op_flows_remove,
    op_flows_update,
)
from apps.flows.src.models.flow_api import FlowCreateRequest
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _create_body(flow_id: str, name: str, prompt: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "catalog command",
        "entry": "main",
        "nodes": {
            "main": {"type": "llm_node", "prompt": prompt, "tools": []},
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }


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


async def test_catalog_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"catalog_cmd_{unique_id}"
    created_http = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json=_create_body(flow_id, "Catalog Command", "first"),
    )
    assert created_http.status_code == 200, created_http.text
    created = created_http.json()
    assert created["flow_id"] == flow_id
    assert created["name"] == "Catalog Command"

    with _system_scope(system_user_id) as user:
        listed = await op_flows_list(
            FlowsListPayload(limit=500, offset=0),
            user=user,
            di=di,
        )
        assert any(item.flow_id == flow_id for item in listed.items)
        item = await op_flows_item(
            FlowsFlowIdPayload(flow_id=flow_id),
            user=user,
            di=di,
        )
        assert item.flow_id == flow_id
        assert item.name == "Catalog Command"
        assert item.entry == "main"

    got_http = await client.get(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert got_http.status_code == 200, got_http.text
    assert got_http.json()["flow_id"] == flow_id
    assert got_http.json()["name"] == "Catalog Command"

    with _system_scope(system_user_id) as user:
        updated = await op_flows_update(
            FlowCreateRequest.model_validate(
                _create_body(flow_id, "Catalog Command Updated", "second")
            ),
            user=user,
            di=di,
        )
        assert updated.name == "Catalog Command Updated"

    put_http = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
        json=_create_body(flow_id, "Catalog Command REST", "third"),
    )
    assert put_http.status_code == 200, put_http.text
    assert put_http.json()["name"] == "Catalog Command REST"

    with _system_scope(system_user_id) as user:
        removed = await op_flows_remove(
            FlowsFlowIdPayload(flow_id=flow_id),
            user=user,
            di=di,
        )
        assert removed.status == "deleted"
        assert removed.flow_id == flow_id

    missing = await client.get(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert missing.status_code == 403


async def test_catalog_create_unknown_tool_is_invalid_payload(
    client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"catalog_bad_tool_{unique_id}"
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Bad tool",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "x",
                    "tools": ["nonexistent_tool_catalog_cmd"],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert "nonexistent_tool_catalog_cmd" in body["detail"]
    assert body["error_code"] == "ws_invalid_payload"
