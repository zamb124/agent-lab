"""
HTTP integration: permissions_enabled=false (default conf).

Enabled-сценарии — tests/flows/core/auth/test_channel_permissions.py.
Checker matrix — tests/flows/core/auth/test_permissions.py.

БЕЗ МОКОВ кроме LLM.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.flows.config import get_settings


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


class TestPermissionsDisabled:
    """Когда permissions_enabled=false (default), доступ разрешён всем."""

    @pytest.mark.asyncio
    async def test_permissions_disabled_allows_access(self, client, flow_with_permission):
        assert get_settings().auth.permissions_enabled is False

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

        assert "result" in data, f"Expected result when permissions disabled, got: {data}"
        assert "error" not in data
