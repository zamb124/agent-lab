"""A2A error codes and capability gates."""

from __future__ import annotations

import uuid

import pytest

from core.a2a.errors import A2AErrorCode
from core.a2a.methods import GET_EXTENDED_AGENT_CARD, GET_TASK
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import post_rpc

pytestmark = [pytest.mark.asyncio]


async def test_error_code_constants_match_spec() -> None:
    assert int(A2AErrorCode.TASK_NOT_FOUND) == -32001
    assert int(A2AErrorCode.TASK_NOT_CANCELABLE) == -32002
    assert int(A2AErrorCode.PUSH_NOTIFICATION_NOT_SUPPORTED) == -32003
    assert int(A2AErrorCode.UNSUPPORTED_OPERATION) == -32004
    assert int(A2AErrorCode.CONTENT_TYPE_NOT_SUPPORTED) == -32005
    assert int(A2AErrorCode.INVALID_AGENT_RESPONSE) == -32006
    assert int(A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED) == -32007
    assert int(A2AErrorCode.EXTENSION_SUPPORT_REQUIRED) == -32008
    assert int(A2AErrorCode.VERSION_NOT_SUPPORTED) == -32009


async def test_get_extended_agent_card_not_configured(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_ext_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(client, flow_id, GET_EXTENDED_AGENT_CARD, {})
        assert "error" in envelope
        assert envelope["error"]["code"] in {
            int(A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED),
            int(A2AErrorCode.UNSUPPORTED_OPERATION),
        }
    finally:
        await delete_flow(client, flow_id)


async def test_unknown_method(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_unk_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(client, flow_id, "TotallyFakeMethod", {"id": "x"})
        assert envelope["error"]["code"] == -32601
    finally:
        await delete_flow(client, flow_id)


async def test_get_task_missing_id_invalid_params(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_params_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(client, flow_id, GET_TASK, {})
        assert "error" in envelope
        assert envelope["error"]["code"] in {-32602, -32001, -32000}
        _ = uuid.uuid4()
    finally:
        await delete_flow(client, flow_id)
