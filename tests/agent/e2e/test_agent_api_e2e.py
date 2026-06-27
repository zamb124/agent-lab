"""E2E HumanitecAgent HTTP API через frontend_service (:9004)."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient

from apps.agent.service import AUDIT_KEY_PREFIX, PAIRING_RATE_PREFIX, REGISTER_RATE_PREFIX
from core.utils.tokens import get_token_service
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    assert_audit_event_in_redis,
    company_id_from_auth_token,
    pair_and_register_device,
    seed_pairing_in_storage,
    user_id_from_auth_token,
)
from tests.agent.fixtures.local_releases import require_local_release_asset_name
from scripts.agent_build import detect_host_platform
from tests.agent._realtime_helpers import connect_agent_tunnel_ws, wait_tunnel_json


@pytest.mark.asyncio
async def test_e2e_download_redirect_local_artifact(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from apps.agent.config import reset_agent_settings
    from pathlib import Path

    reset_agent_settings()
    artifact_path = Path(agent_local_release_artifact)
    asset_name = require_local_release_asset_name(artifact_path)
    platform_name = detect_host_platform()
    response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert "/releases/artifact/" in location
    assert asset_name in location or platform_name in location


@pytest.mark.asyncio
async def test_e2e_releases_status_ready(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from apps.agent.config import reset_agent_settings
    from pathlib import Path

    reset_agent_settings()
    _ = require_local_release_asset_name(Path(agent_local_release_artifact))
    response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/releases/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_e2e_releases_status_github_404(
    agent_release_github_missing_repo: None,
) -> None:
    from apps.agent.config import reset_agent_settings
    from apps.agent.service import fetch_latest_release_status

    _ = agent_release_github_missing_repo
    reset_agent_settings()
    status = await fetch_latest_release_status()
    assert status.ready is False


@pytest.mark.asyncio
async def test_e2e_download_asset_name_mismatch(
    agent_release_github_missing_repo: None,
) -> None:
    import httpx

    from apps.agent.config import reset_agent_settings
    from apps.agent.service import fetch_latest_release_asset_url
    from scripts.agent_build import detect_host_platform

    _ = agent_release_github_missing_repo
    reset_agent_settings()
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_latest_release_asset_url(detect_host_platform())


@pytest.mark.asyncio
async def test_e2e_pairing_unauthorized(agent_frontend_http_anon: AsyncClient) -> None:
    response = await agent_frontend_http_anon.post(f"{AGENT_API_PREFIX}/pairing")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_e2e_create_pairing_code_rate_limit(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    user_id = user_id_from_auth_token(auth_token)
    rate_key = f"{PAIRING_RATE_PREFIX}{user_id}"
    await frontend_container.redis_client.delete(rate_key)
    from apps.agent.config import get_agent_settings

    settings = get_agent_settings()
    for _ in range(settings.pairing_rate_limit_per_hour):
        response = await agent_frontend_http_client.post(f"{AGENT_API_PREFIX}/pairing")
        assert response.status_code == 200
    response = await agent_frontend_http_client.post(f"{AGENT_API_PREFIX}/pairing")
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_e2e_list_devices_unauthorized(agent_frontend_http_anon: AsyncClient) -> None:
    response = await agent_frontend_http_anon.get(f"{AGENT_API_PREFIX}/devices")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_e2e_register_url_bundle(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    from apps.frontend.config import get_frontend_public_base_url
    from tests.agent._helpers import create_pairing_via_http, register_device_via_http

    pairing_body = await create_pairing_via_http(
        agent_frontend_http_client,
        auth_cookie=auth_token,
    )
    pairing_code = pairing_body["pairing_code"]
    assert isinstance(pairing_code, str)

    register_body = await register_device_via_http(
        agent_frontend_http_client,
        pairing_code=pairing_code,
        device_id=f"device-{unique_id}",
        device_name=f"Device {unique_id}",
        os_name="darwin",
        hostname=f"host-{unique_id}",
    )
    frontend_base = get_frontend_public_base_url().rstrip("/")
    assert register_body["frontend_base_url"] == frontend_base
    assert register_body["platform_mcp_url"] == (
        f"{frontend_base}/flows/api/v1/agent/platform-mcp"
    )
    assert register_body["tunnel_ws_url"] == (
        f"{frontend_base.replace('https://', 'wss://').replace('http://', 'ws://')}"
        f"/frontend/api/agent/tunnel"
    )
    assert isinstance(register_body["company_id"], str) and register_body["company_id"]
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None
    company_response = await agent_frontend_http_client.get("/frontend/api/companies/me")
    company_response.raise_for_status()
    company_payload = company_response.json()
    company_items = company_payload["items"]
    active = next(
        (item for item in company_items if item["company_id"] == token_data.company_id),
        None,
    )
    assert active is not None
    assert register_body["company_subdomain"] == active["subdomain"]
    llm = register_body["llm"]
    assert isinstance(llm, dict)
    assert llm["provider_id"] == "humanitec"
    assert llm["model_id"] == "auto"
    assert llm["api_base_url"] == f"{frontend_base}/flows/api/v1/agent/llm/v1"


@pytest.mark.asyncio
async def test_e2e_register_rejects_disallowed_origin(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import create_pairing_via_http

    pairing_body = await create_pairing_via_http(
        agent_frontend_http_client,
        auth_cookie=auth_token,
    )
    pairing_code = pairing_body["pairing_code"]
    assert isinstance(pairing_code, str)

    response = await agent_frontend_http_client.post(
        f"{AGENT_API_PREFIX}/register",
        params={"origin": "https://evil.example.com"},
        json={
            "pairing_code": pairing_code,
            "device_id": f"device-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 400
    assert "origin" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_e2e_register_allowed_origin_override(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import create_pairing_via_http

    allowed_origin = "http://system.lvh.me:9004"
    discover_response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/discover",
        params={"origin": allowed_origin},
    )
    assert discover_response.status_code == 200
    discover_body = discover_response.json()
    assert discover_body["frontend_base_url"] == allowed_origin
    assert discover_body["tunnel_ws_url"] == "ws://system.lvh.me:9004/frontend/api/agent/tunnel"

    pairing_body = await create_pairing_via_http(
        agent_frontend_http_client,
        auth_cookie=auth_token,
    )
    pairing_code = pairing_body["pairing_code"]
    device_id = f"device-origin-{unique_id}"
    register_response = await agent_frontend_http_client.post(
        f"{AGENT_API_PREFIX}/register",
        params={"origin": allowed_origin},
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": f"Origin {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register_response.status_code == 200
    register_body = register_response.json()
    assert register_body["frontend_base_url"] == allowed_origin
    assert register_body["platform_mcp_url"] == (
        f"{allowed_origin}/flows/api/v1/agent/platform-mcp"
    )


@pytest.mark.asyncio
async def test_e2e_pair_register_list_audit(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    list_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert any(item["device_id"] == device_id for item in items)

    audit_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/audit")
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["items"]
    event_types = {item["event_type"] for item in audit_items}
    assert "agent.device_registered" in event_types

    company_id = company_id_from_auth_token(auth_token)
    audit_key = f"{AUDIT_KEY_PREFIX}{company_id}"
    raw_audit = await frontend_container.redis_client.lrange(audit_key, 0, -1)
    assert len(raw_audit) >= 1


@pytest.mark.asyncio
async def test_e2e_register_incomplete_pairing_data(
    agent_frontend_http_anon: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    pairing_code = "333333"
    key = f"agent_pairing:{pairing_code}"
    await frontend_container.shared_storage.set(key, json.dumps({"user_id": "only-user"}), force_global=True)
    response = await agent_frontend_http_anon.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": f"device-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Неполные данные pairing code"
    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_e2e_revoke_device_not_found(
    agent_frontend_http_client: AsyncClient,
    unique_id: str,
) -> None:
    response = await agent_frontend_http_client.delete(f"{AGENT_API_PREFIX}/devices/missing-{unique_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_e2e_register_expired_pairing_code(
    agent_frontend_http_anon: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    pairing_code = "888888"
    user_id = user_id_from_auth_token(auth_token)
    company_id = company_id_from_auth_token(auth_token)
    await seed_pairing_in_storage(
        frontend_container,
        pairing_code=pairing_code,
        user_id=user_id,
        company_id=company_id,
        ttl_seconds=1,
    )
    await asyncio.sleep(2)
    response = await agent_frontend_http_anon.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": f"device-expired-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Недействительный или истёкший pairing code"


@pytest.mark.asyncio
async def test_e2e_register_rate_limit_429(
    agent_frontend_http_anon: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    from apps.agent.config import get_agent_settings

    device_id = f"device-rate-{unique_id}"
    client_key = f"127.0.0.1:{device_id}"
    rate_key = f"{REGISTER_RATE_PREFIX}{client_key}"
    await frontend_container.redis_client.delete(rate_key)
    settings = get_agent_settings()
    register_payload = {
        "pairing_code": "000000",
        "device_id": device_id,
        "device_name": f"Device {unique_id}",
        "os": "darwin",
        "hostname": f"host-{unique_id}",
    }
    for _ in range(settings.register_rate_limit_per_hour):
        response = await agent_frontend_http_anon.post(
            f"{AGENT_API_PREFIX}/register",
            json=register_payload,
        )
        assert response.status_code == 400
    response = await agent_frontend_http_anon.post(
        f"{AGENT_API_PREFIX}/register",
        json=register_payload,
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "Превышен лимит регистрации устройств. Попробуйте позже."


@pytest.mark.asyncio
async def test_e2e_list_devices_tunnel_online(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        await websocket.send(json.dumps({"type": "ping"}))
        await wait_tunnel_json(websocket, expected_type="pong", timeout=5.0)

        list_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        device_item = next(item for item in items if item["device_id"] == device_id)
        assert device_item["is_tunnel_online"] is True


@pytest.mark.asyncio
async def test_e2e_revoke_device_wrong_company(
    agent_frontend_http_client: AsyncClient,
    agent_frontend_http_company2: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    response = await agent_frontend_http_company2.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Устройство не найдено"


@pytest.mark.asyncio
async def test_e2e_update_device_policy_all_fields(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    from apps.agent.service import DEVICE_KEY_PREFIX

    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    policy_payload = {
        "allowed_roots": ["/tmp", "/var/data"],
        "exec_whitelist": ["git", "npm"],
        "exec_require_confirm": False,
        "shell_enabled": True,
        "browser_enabled": False,
        "max_file_size_mb": 100,
        "audit_retention_days": 90,
    }
    patch_response = await agent_frontend_http_client.patch(
        f"{AGENT_API_PREFIX}/devices/{device_id}/policy",
        json={"policy": policy_payload},
    )
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["policy"] == policy_payload

    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    stored_raw = await frontend_container.shared_storage.get(device_key, force_global=True)
    assert stored_raw is not None
    stored_policy = json.loads(stored_raw)["policy"]
    assert stored_policy == policy_payload


@pytest.mark.asyncio
async def test_e2e_update_device_policy_not_found(
    agent_frontend_http_client: AsyncClient,
    unique_id: str,
) -> None:
    response = await agent_frontend_http_client.patch(
        f"{AGENT_API_PREFIX}/devices/missing-policy-{unique_id}/policy",
        json={
            "policy": {
                "allowed_roots": ["/tmp"],
                "exec_whitelist": [],
                "exec_require_confirm": True,
                "shell_enabled": True,
                "browser_enabled": True,
                "max_file_size_mb": 50,
                "audit_retention_days": 30,
            },
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Устройство не найдено"


@pytest.mark.asyncio
async def test_e2e_audit_pairing_created(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
) -> None:
    response = await agent_frontend_http_client.post(f"{AGENT_API_PREFIX}/pairing")
    assert response.status_code == 200
    company_id = company_id_from_auth_token(auth_token)
    await assert_audit_event_in_redis(
        frontend_container,
        company_id=company_id,
        event_type="agent.pairing_created",
    )


@pytest.mark.asyncio
async def test_e2e_audit_device_revoked(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    revoke_response = await agent_frontend_http_client.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert revoke_response.status_code == 204
    company_id = company_id_from_auth_token(auth_token)
    await assert_audit_event_in_redis(
        frontend_container,
        company_id=company_id,
        event_type="agent.device_revoked",
    )


@pytest.mark.asyncio
async def test_e2e_audit_policy_updated(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    patch_response = await agent_frontend_http_client.patch(
        f"{AGENT_API_PREFIX}/devices/{device_id}/policy",
        json={
            "policy": {
                "allowed_roots": ["/opt"],
                "exec_whitelist": [],
                "exec_require_confirm": True,
                "shell_enabled": True,
                "browser_enabled": True,
                "max_file_size_mb": 50,
                "audit_retention_days": 30,
            },
        },
    )
    assert patch_response.status_code == 200
    company_id = company_id_from_auth_token(auth_token)
    await assert_audit_event_in_redis(
        frontend_container,
        company_id=company_id,
        event_type="agent.device_policy_updated",
    )
