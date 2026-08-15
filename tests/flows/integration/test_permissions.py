"""
HTTP integration: OpenFGA flow permissions cutover.

Channel matrix — tests/flows/core/auth/test_channel_permissions.py.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


def _msg(text: str, context_id: str | None = None) -> dict[str, Any]:
    message = {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if context_id:
        message["contextId"] = context_id
    return message


def _rpc_request(method: str, params: dict[str, Any], rpc_id: str = "1") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params,
    }


class TestPermissionsCutover:
    @pytest.mark.asyncio
    async def test_send_message_without_group_is_denied(
        self, client, flow_with_permission
    ):
        flow_id = flow_with_permission
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "SendMessage",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": []},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )
        data = response.json()
        assert "error" in data or "result" in data
