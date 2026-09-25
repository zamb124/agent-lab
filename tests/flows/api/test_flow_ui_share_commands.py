"""Prod-like: live Flow UI shares — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.flow_ui_share_operations import (
    op_flows_flow_ui_shares_create,
    op_flows_flow_ui_shares_list,
    op_flows_flow_ui_shares_remove,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.flow_ui_share import (
    FlowUIShareCreatePayload,
    FlowUIShareGrantIdPayload,
    FlowUIShareListPayload,
)
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.flows._flow_ui_session import a2a_send, text_message
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]

SHARES = "/flows/api/v1/flow-ui/shares"
_HOST = {"Host": "linnex.io"}


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


async def _open_session(client: AsyncClient, *, flow_id: str, context_id: str) -> None:
    await create_echo_flow(client, flow_id)
    task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hello"),
    )
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task


async def test_flow_ui_shares_create_list_remove_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    flow_id = f"share_cmd_{unique_id}"
    context_id = f"ctx-cmd-{unique_id}"
    await _open_session(client, flow_id=flow_id, context_id=context_id)
    try:
        created = await client.post(
            SHARES,
            headers=_HOST,
            json={
                "flow_id": flow_id,
                "context_id": context_id,
                "permission": "viewer",
                "redacted_paths": ["/secret"],
                "expires_in_seconds": 300,
            },
        )
        assert created.status_code == 200, created.text
        grant_id = created.json()["grant"]["grant_id"]
        list_payload = FlowUIShareListPayload(flow_id=flow_id, context_id=context_id)

        listed = await client.get(SHARES, params={"flow_id": flow_id, "context_id": context_id})
        assert listed.status_code == 200, listed.text
        with _system_scope(system_user_id) as user:
            op_listed = await op_flows_flow_ui_shares_list(
                list_payload, user=user, di=di
            )
        assert listed.json() == op_listed.model_dump(mode="json")
        assert listed.json()["items"][0]["grant_id"] == grant_id
        assert created.json()["grant"] == listed.json()["items"][0]

        revoked = await client.delete(f"{SHARES}/{grant_id}")
        assert revoked.status_code == 200, revoked.text
        assert revoked.json() == {"status": "deleted", "grant_id": grant_id}
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as raised:
                await op_flows_flow_ui_shares_remove(
                    FlowUIShareGrantIdPayload(grant_id=grant_id),
                    user=user,
                    di=di,
                )
        assert raised.value.code == "not_found"
    finally:
        await delete_flow(client, flow_id)


async def test_flow_ui_shares_create_missing_session_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    flow_id = f"share_miss_{unique_id}"
    context_id = f"ctx-miss-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        http = await client.post(
            SHARES,
            headers=_HOST,
            json={"flow_id": flow_id, "context_id": context_id, "permission": "viewer"},
        )
        assert http.status_code == 409, http.text
        assert http.json()["error_code"] == "conflict"
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as raised:
                await op_flows_flow_ui_shares_create(
                    FlowUIShareCreatePayload(
                        flow_id=flow_id,
                        context_id=context_id,
                        public_host="linnex.io",
                    ),
                    user=user,
                    di=di,
                )
        assert raised.value.code == "conflict"
    finally:
        await delete_flow(client, flow_id)


async def test_flow_ui_shares_create_without_host_is_invalid(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    flow_id = f"share_host_{unique_id}"
    context_id = f"ctx-host-{unique_id}"
    await _open_session(client, flow_id=flow_id, context_id=context_id)
    try:
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as raised:
                await op_flows_flow_ui_shares_create(
                    FlowUIShareCreatePayload(
                        flow_id=flow_id,
                        context_id=context_id,
                        public_host="",
                    ),
                    user=user,
                    di=di,
                )
        assert raised.value.code == "ws_invalid_payload"
    finally:
        await delete_flow(client, flow_id)
