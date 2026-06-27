"""
HTTP helpers для HumanitecAgent тестов.
"""

from __future__ import annotations

import json

from httpx import AsyncClient

from core.utils.tokens import get_token_service

AGENT_API_PREFIX = "/frontend/api/agent"
AGENT_TEST_PUBLIC_ORIGIN = "http://system.lvh.me:9004"
FRONTEND_HTTP_BASE = AGENT_TEST_PUBLIC_ORIGIN
FRONTEND_TUNNEL_POD_ID = "frontend-e2e-pod"
FLOWS_HTTP_BASE = "http://127.0.0.1:9001"
PLATFORM_MCP_PATH = "/flows/api/v1/agent/platform-mcp"
LLM_MODELS_PATH = "/flows/api/v1/agent/llm/v1/models"
LLM_CHAT_COMPLETIONS_PATH = "/flows/api/v1/agent/llm/v1/chat/completions"


async def create_pairing_via_http(
    client: AsyncClient,
    *,
    auth_cookie: str | None = None,
) -> dict[str, object]:
    headers: dict[str, str] = {}
    if auth_cookie is not None:
        headers["Cookie"] = f"auth_token={auth_cookie}"
    response = await client.post(f"{AGENT_API_PREFIX}/pairing", headers=headers)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("pairing response must be object")
    return body


async def register_device_via_http(
    client: AsyncClient,
    *,
    pairing_code: str,
    device_id: str,
    device_name: str,
    os_name: str,
    hostname: str,
) -> dict[str, object]:
    response = await client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": device_name,
            "os": os_name,
            "hostname": hostname,
        },
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("register response must be object")
    return body


async def pair_and_register_device(
    client: AsyncClient,
    *,
    auth_cookie: str,
    unique_id: str,
) -> tuple[str, str]:
    pairing_body = await create_pairing_via_http(client, auth_cookie=auth_cookie)
    pairing_code = pairing_body.get("pairing_code")
    if not isinstance(pairing_code, str) or len(pairing_code) != 6:
        raise AssertionError("pairing_code invalid")
    device_id = f"device-{unique_id}"
    register_body = await register_device_via_http(
        client,
        pairing_code=pairing_code,
        device_id=device_id,
        device_name=f"Device {unique_id}",
        os_name="darwin",
        hostname=f"host-{unique_id}",
    )
    token = register_body.get("token")
    if not isinstance(token, str) or not token:
        raise AssertionError("device token missing")
    return device_id, token


def user_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.user_id


def company_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.company_id


async def seed_pairing_in_storage(
    frontend_container,
    *,
    pairing_code: str,
    user_id: str,
    company_id: str,
    ttl_seconds: int | None = None,
) -> None:
    key = f"agent_pairing:{pairing_code}"
    payload = json.dumps({"user_id": user_id, "company_id": company_id})
    await frontend_container.shared_storage.set(
        key,
        payload,
        ttl=ttl_seconds,
        force_global=True,
    )


async def assert_audit_event_in_redis(
    frontend_container,
    *,
    company_id: str,
    event_type: str,
) -> None:
    from apps.agent.service import AUDIT_KEY_PREFIX

    audit_key = f"{AUDIT_KEY_PREFIX}{company_id}"
    raw_items = await frontend_container.redis_client.lrange(audit_key, 0, -1)
    for raw_item in raw_items:
        payload = json.loads(raw_item)
        if isinstance(payload, dict) and payload.get("event_type") == event_type:
            return
    raise AssertionError(f"audit event {event_type!r} not found for company {company_id}")


async def ensure_example_react_flow(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_{unique_id}"
    response = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json={
            "flow_id": flow_id,
            "name": f"Agent MCP {unique_id}",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Reply briefly to the user.",
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text
    return flow_id
