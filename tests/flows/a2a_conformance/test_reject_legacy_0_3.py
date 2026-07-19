"""Hard cut: A2A 0.3 method names and Part shapes MUST fail."""

from __future__ import annotations

import uuid

import pytest

from tests.flows._a2a_v1 import A2A_HEADERS, a2a_headers
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import post_rpc

pytestmark = [pytest.mark.asyncio]


@pytest.mark.parametrize(
    "method",
    [
        "message/send",
        "message/stream",
        "tasks/get",
        "tasks/cancel",
        "tasks/resubscribe",
        "tasks/pushNotificationConfig/set",
        "agent/getAuthenticatedExtendedCard",
    ],
)
async def test_legacy_method_names_are_rejected(
    client, unique_id: str, method: str
) -> None:
    flow_id = f"a2a_conf_reject_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(
            client,
            flow_id,
            method,
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": "x"}],
                }
            },
        )
        assert "error" in envelope, envelope
        assert envelope["error"]["code"] == -32601
    finally:
        await delete_flow(client, flow_id)


async def test_legacy_kind_text_part_is_rejected(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_reject_kind_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(
            client,
            flow_id,
            "SendMessage",
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"kind": "text", "text": "legacy"}],
                }
            },
        )
        assert "error" in envelope, envelope
        assert envelope["error"]["code"] in {-32602, -32000, -32600}
    finally:
        await delete_flow(client, flow_id)


async def test_legacy_role_user_is_rejected(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_reject_role_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(
            client,
            flow_id,
            "SendMessage",
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "user",
                    "parts": [{"text": "legacy-role"}],
                }
            },
        )
        assert "error" in envelope, envelope
    finally:
        await delete_flow(client, flow_id)


async def test_unsupported_a2a_version_header(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_reject_ver_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers={"A2A-Version": "0.3"},
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": "x"}],
                    }
                },
            },
        )
        assert response.status_code == 200, response.text
        envelope = response.json()
        assert envelope["error"]["code"] == -32009
    finally:
        await delete_flow(client, flow_id)
