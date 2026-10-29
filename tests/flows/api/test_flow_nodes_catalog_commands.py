"""Prod-like: каталог NodeConfig — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.node_operations import (
    op_flows_nodes_catalog_create,
    op_flows_nodes_catalog_item,
    op_flows_nodes_catalog_list,
    op_flows_nodes_catalog_remove,
    op_flows_nodes_catalog_update,
)
from apps.flows.src.models.node_config import NodeConfig, NodeIdPayload, NodeListPayload
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _llm_node(node_id: str, *, name: str, prompt: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "type": "llm_node",
        "name": name,
        "description": "catalog command",
        "prompt": prompt,
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


async def test_nodes_catalog_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    node_id = f"node_cmd_{unique_id}"
    created_http = await client.post(
        "/flows/api/v1/nodes",
        headers=auth_headers_system,
        json=_llm_node(node_id, name="Echo", prompt="hi"),
    )
    assert created_http.status_code == 200, created_http.text
    created = NodeConfig.model_validate(created_http.json())
    assert created.node_id == node_id
    assert created.name == "Echo"
    assert created.prompt == "hi"

    with _system_scope(system_user_id) as user:
        listed = await op_flows_nodes_catalog_list(
            NodeListPayload(limit=200, offset=0),
            user=user,
            di=di,
        )
        assert any(item.node_id == node_id for item in listed.items)
        item = await op_flows_nodes_catalog_item(
            NodeIdPayload(node_id=node_id),
            user=user,
            di=di,
        )
        assert item.model_dump(mode="json") == created_http.json()

    listed_http = await client.get("/flows/api/v1/nodes", headers=auth_headers_system)
    assert listed_http.status_code == 200, listed_http.text
    listed_page = OffsetPage[NodeConfig].model_validate(listed_http.json())
    assert any(item.node_id == node_id for item in listed_page.items)

    with _system_scope(system_user_id) as user:
        updated = await op_flows_nodes_catalog_update(
            NodeConfig.model_validate(_llm_node(node_id, name="Renamed", prompt="hello")),
            user=user,
            di=di,
        )
        assert updated.name == "Renamed"
        assert updated.prompt == "hello"

    put_http = await client.put(
        f"/flows/api/v1/nodes/{node_id}",
        headers=auth_headers_system,
        json=_llm_node(node_id, name="REST", prompt="third"),
    )
    assert put_http.status_code == 200, put_http.text
    assert put_http.json()["name"] == "REST"

    with _system_scope(system_user_id) as user:
        fetched = await op_flows_nodes_catalog_item(
            NodeIdPayload(node_id=node_id),
            user=user,
            di=di,
        )
        assert fetched.model_dump(mode="json") == put_http.json()
        removed = await op_flows_nodes_catalog_remove(
            NodeIdPayload(node_id=node_id),
            user=user,
            di=di,
        )
        assert removed.status == "deleted"
        assert removed.node_id == node_id

    missing = await client.get(f"/flows/api/v1/nodes/{node_id}", headers=auth_headers_system)
    assert missing.status_code == 404


async def test_nodes_catalog_create_op_matches_rest_conflict(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    node_id = f"node_dup_cmd_{unique_id}"
    first = await client.post(
        "/flows/api/v1/nodes",
        headers=auth_headers_system,
        json=_llm_node(node_id, name="One", prompt="a"),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/flows/api/v1/nodes",
        headers=auth_headers_system,
        json=_llm_node(node_id, name="Two", prompt="b"),
    )
    assert second.status_code == 409
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError, match="already exists"):
            await op_flows_nodes_catalog_create(
                NodeConfig.model_validate(_llm_node(node_id, name="Two", prompt="b")),
                user=user,
                di=di,
            )
