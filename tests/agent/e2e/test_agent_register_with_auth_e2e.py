"""E2E register-with-auth и discover llm bundle."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.frontend.config import get_frontend_public_base_url
from core.utils.tokens import get_token_service
from tests.agent._helpers import AGENT_API_PREFIX

pytestmark = pytest.mark.asyncio


async def test_e2e_discover_includes_llm_api_url(
    agent_frontend_http_client: AsyncClient,
) -> None:
    response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/discover")
    assert response.status_code == 200
    body = response.json()
    frontend_base = get_frontend_public_base_url().rstrip("/")
    assert body["llm_api_url"] == f"{frontend_base}/flows/api/v1/agent/llm/v1"


async def test_e2e_register_with_auth_returns_llm_bundle(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    frontend_base = get_frontend_public_base_url().rstrip("/")
    response = await agent_frontend_http_client.post(
        f"{AGENT_API_PREFIX}/register-with-auth",
        json={
            "device_id": f"auth-device-{unique_id}",
            "device_name": f"Auth Device {unique_id}",
            "os": "darwin",
            "hostname": f"auth-host-{unique_id}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["token"], str) and body["token"]
    llm = body["llm"]
    assert isinstance(llm, dict)
    assert llm["provider_id"] == "humanitec"
    assert llm["model_id"] == "auto"
    assert llm["api_base_url"] == f"{frontend_base}/flows/api/v1/agent/llm/v1"

    token_data = get_token_service().validate_token(body["token"])
    assert token_data is not None
    assert token_data.metadata.get("token_purpose") == "device"
    assert token_data.metadata.get("device_id") == f"auth-device-{unique_id}"


async def test_e2e_register_with_auth_unauthorized(
    agent_frontend_http_anon: AsyncClient,
    unique_id: str,
) -> None:
    response = await agent_frontend_http_anon.post(
        f"{AGENT_API_PREFIX}/register-with-auth",
        json={
            "device_id": f"auth-anon-{unique_id}",
            "device_name": "Anon",
            "os": "darwin",
            "hostname": "host",
        },
    )
    assert response.status_code == 401
