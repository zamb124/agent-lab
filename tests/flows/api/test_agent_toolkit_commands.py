"""Prod-like: manage AgentToolkit — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.agent_toolkit_operations import (
    op_flows_agent_toolkits_item,
    op_flows_agent_toolkits_list,
    op_flows_agent_toolkits_remove,
)
from apps.flows.src.models.agent_toolkit import (
    AgentToolkit,
    AgentToolkitCreateRequest,
    AgentToolkitIdPayload,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import EmptyPayload, WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]

MANAGE = "/flows/api/v1/agent/toolkits/manage"


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
            active_namespace="default",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


def _create_body(toolkit_id: str) -> AgentToolkitCreateRequest:
    return AgentToolkitCreateRequest(
        toolkit_id=toolkit_id,
        name="Command toolkit",
        description="REST==op",
        default_enabled=False,
        position=100,
        flow_ids=[],
        tool_ids=["calculator"],
    )


async def test_agent_toolkits_list_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http = await client.get(MANAGE, headers=auth_headers_system)
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        listed = await op_flows_agent_toolkits_list(
            EmptyPayload(),
            user=user,
            di=di,
        )
    assert http.json() == listed.model_dump(mode="json")


async def test_agent_toolkits_item_create_update_remove_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    toolkit_id = f"tk_cmd_{unique_id}"
    created = await client.post(
        MANAGE,
        headers=auth_headers_system,
        json=_create_body(toolkit_id).model_dump(mode="json"),
    )
    assert created.status_code == 200, created.text
    try:
        with _system_scope(system_user_id) as user:
            op_item = await op_flows_agent_toolkits_item(
                AgentToolkitIdPayload(toolkit_id=toolkit_id),
                user=user,
                di=di,
            )
        assert created.json() == op_item.model_dump(mode="json")
        _ = AgentToolkit.model_validate(created.json())

        http_get = await client.get(f"{MANAGE}/{toolkit_id}", headers=auth_headers_system)
        assert http_get.status_code == 200, http_get.text
        assert http_get.json() == op_item.model_dump(mode="json")

        updated = await client.put(
            f"{MANAGE}/{toolkit_id}",
            headers=auth_headers_system,
            json={
                "name": "Command toolkit updated",
                "description": "Updated",
                "default_enabled": True,
                "position": 101,
                "flow_ids": [],
                "tool_ids": ["calculator", "rag_search"],
            },
        )
        assert updated.status_code == 200, updated.text
        with _system_scope(system_user_id) as user:
            op_updated = await op_flows_agent_toolkits_item(
                AgentToolkitIdPayload(toolkit_id=toolkit_id),
                user=user,
                di=di,
            )
        assert updated.json() == op_updated.model_dump(mode="json")
        assert updated.json()["name"] == "Command toolkit updated"
    finally:
        deleted = await client.delete(f"{MANAGE}/{toolkit_id}", headers=auth_headers_system)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"status": "deleted", "toolkit_id": toolkit_id}
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as raised:
                await op_flows_agent_toolkits_item(
                    AgentToolkitIdPayload(toolkit_id=toolkit_id),
                    user=user,
                    di=di,
                )
        assert raised.value.code == "not_found"


async def test_agent_toolkits_item_missing_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    missing_id = f"tk_missing_{unique_id}"
    http = await client.get(f"{MANAGE}/{missing_id}", headers=auth_headers_system)
    assert http.status_code == 404, http.text
    assert http.json()["error_code"] == "not_found"
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_agent_toolkits_item(
                AgentToolkitIdPayload(toolkit_id=missing_id),
                user=user,
                di=di,
            )
    assert raised.value.code == "not_found"


async def test_agent_toolkits_remove_platform_forbidden_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    toolkit_id = f"tk_plat_{unique_id}"
    with _system_scope(system_user_id):
        _ = await AgentToolkit.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Platform locked",
                description="Cannot delete",
                source="platform",
            )
        )
    try:
        http = await client.delete(f"{MANAGE}/{toolkit_id}", headers=auth_headers_system)
        assert http.status_code == 403, http.text
        assert http.json()["error_code"] == "forbidden"
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as raised:
                await op_flows_agent_toolkits_remove(
                    AgentToolkitIdPayload(toolkit_id=toolkit_id),
                    user=user,
                    di=di,
                )
        assert raised.value.code == "forbidden"
    finally:
        with _system_scope(system_user_id):
            _ = await AgentToolkit.delete_by_toolkit_id(toolkit_id)
