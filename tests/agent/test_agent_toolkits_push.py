"""Push-уведомления и toolkits_url для AgentToolkit."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient

from apps.flows.src.services.agent_toolkit_notify import TUNNEL_TOOLKITS_UPDATED_CHANNEL
from core.platform_brand.resolver import platform_public_base_url
from tests.agent._helpers import AGENT_API_PREFIX


async def _wait_pubsub_message(pubsub, *, timeout_seconds: float) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is None:
            continue
        if message.get("type") == "message":
            return message
    raise TimeoutError("pubsub message not received")


@pytest.mark.asyncio
async def test_manage_create_publishes_toolkits_updated(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    unique_id: str,
) -> None:
    from tests.agent._helpers import company_id_from_auth_token

    auth_token = auth_headers["Authorization"].removeprefix("Bearer ").strip()
    company_id = company_id_from_auth_token(auth_token)
    pubsub = await container.redis_client.open_pubsub()
    await pubsub.subscribe(TUNNEL_TOOLKITS_UPDATED_CHANNEL)
    toolkit_id = f"tk_push_{unique_id}"
    try:
        create_task = asyncio.create_task(
            flows_client.post(
                "/flows/api/v1/agent/toolkits/manage",
                headers=auth_headers,
                json={
                    "toolkit_id": toolkit_id,
                    "name": "Push test",
                    "description": "Push test",
                    "flow_ids": [],
                    "tool_ids": [],
                },
            )
        )
        message = await _wait_pubsub_message(pubsub, timeout_seconds=10.0)
        response = await create_task
        assert response.status_code == 200, response.text
        payload = json.loads(message["data"])
        assert payload["company_id"] == company_id
    finally:
        await pubsub.unsubscribe(TUNNEL_TOOLKITS_UPDATED_CHANNEL)
        await pubsub.aclose()
        await flows_client.delete(
            f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
            headers=auth_headers,
        )


@pytest.mark.asyncio
async def test_push_toolkits_updated_to_tunnel_socket(unique_id: str) -> None:
    from apps.agent.tunnel_registry import (
        push_toolkits_updated_to_tunnel,
        register_tunnel_socket,
        unregister_tunnel_socket,
    )

    device_id = f"device_push_{unique_id}"

    class _TunnelSocket:
        def __init__(self) -> None:
            self.sent_frames: list[str] = []

        async def send_text(self, data: str) -> None:
            self.sent_frames.append(data)

    tunnel_socket = _TunnelSocket()
    register_tunnel_socket(device_id, tunnel_socket)
    try:
        await push_toolkits_updated_to_tunnel(device_id)
        assert len(tunnel_socket.sent_frames) == 1
        frame = json.loads(tunnel_socket.sent_frames[0])
        assert frame == {"type": "toolkits_updated"}
    finally:
        unregister_tunnel_socket(device_id)


@pytest.mark.asyncio
async def test_register_includes_toolkits_url(
    frontend_client_with_auth: AsyncClient,
    unique_id: str,
) -> None:
    pairing = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing.status_code == 200, pairing.text
    pairing_code = pairing.json()["pairing_code"]
    register = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": f"device_toolkits_{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register.status_code == 200, register.text
    body = register.json()
    frontend_base = platform_public_base_url().rstrip("/")
    assert body["toolkits_url"] == f"{frontend_base}/flows/api/v1/agent/toolkits"


@pytest.mark.asyncio
async def test_discover_includes_toolkits_url(
    frontend_client: AsyncClient,
) -> None:
    response = await frontend_client.get(f"{AGENT_API_PREFIX}/discover")
    assert response.status_code == 200
    body = response.json()
    frontend_base = platform_public_base_url().rstrip("/")
    assert body["toolkits_url"] == f"{frontend_base}/flows/api/v1/agent/toolkits"
