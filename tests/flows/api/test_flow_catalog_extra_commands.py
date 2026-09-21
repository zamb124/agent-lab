"""Prod-like: store/validate/versions REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.realtime.operations import (
    FlowsFlowIdPayload,
    FlowsFlowVersionPayload,
    op_flows_store_bundles,
    op_flows_validate,
    op_flows_version_item,
    op_flows_versions_list,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.flow_api import FlowValidateRequest
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import EmptyPayload
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


async def test_store_bundles_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/flows/store/bundles",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_items = http_resp.json()["items"]
    assert isinstance(http_items, list)
    assert len(http_items) > 0
    with _system_scope(system_user_id) as user:
        listed = await op_flows_store_bundles(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert [item.model_dump() for item in listed.items] == http_items


async def test_validate_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    body = {
        "entry": "main",
        "nodes": {"main": {"type": "llm_node", "prompt": "ok", "tools": []}},
        "edges": [{"from_node": "main", "to_node": None}],
        "variables": {},
    }
    http_resp = await client.post(
        "/flows/api/v1/flows/validate",
        headers=auth_headers_system,
        json=body,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_json = http_resp.json()
    assert http_json["valid"] is True
    with _system_scope(system_user_id) as user:
        validated = await op_flows_validate(
            FlowValidateRequest.model_validate(body),
            user=user,
            container=container,
        )
    assert validated.valid is True
    assert validated.model_dump() == http_json


async def test_versions_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"catalog_ver_{unique_id}"
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Versions Command",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "v1", "tools": []}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert created.status_code == 200, created.text
    versions_http = await client.get(
        f"/flows/api/v1/flows/{flow_id}/versions",
        headers=auth_headers_system,
    )
    assert versions_http.status_code == 200, versions_http.text
    version_ids = versions_http.json()["items"]
    assert len(version_ids) >= 1
    first = version_ids[0]
    with _system_scope(system_user_id) as user:
        listed = await op_flows_versions_list(
            FlowsFlowIdPayload(flow_id=flow_id),
            user=user,
            container=container,
        )
        assert listed.items == version_ids
        item = await op_flows_version_item(
            FlowsFlowVersionPayload(flow_id=flow_id, version=first),
            user=user,
            container=container,
        )
    item_http = await client.get(
        f"/flows/api/v1/flows/{flow_id}/versions/{first}",
        headers=auth_headers_system,
    )
    assert item_http.status_code == 200, item_http.text
    assert item.flow_id == flow_id
    assert item.model_dump() == item_http.json()
