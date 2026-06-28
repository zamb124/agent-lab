"""
HTTP-тесты HumanitecAgent API на frontend сервисе.
"""

import json
import uuid

import pytest
from httpx import AsyncClient

from apps.agent.models import AgentDeviceRecord
from apps.agent.service import DEVICE_KEY_PREFIX, PAIRING_CODE_PREFIX
from apps.frontend.config import get_frontend_public_base_url
from core.models.identity_models import User
from core.utils.tokens import get_token_service

AGENT_API_PREFIX = "/frontend/api/agent"


async def _seed_agent_pairing(
    frontend_container,
    *,
    pairing_code: str,
    user_id: str,
    company_id: str,
) -> None:
    key = f"{PAIRING_CODE_PREFIX}{pairing_code}"
    payload = json.dumps({"user_id": user_id, "company_id": company_id})
    await frontend_container.shared_storage.set(key, payload, force_global=True)


@pytest.mark.asyncio
async def test_agent_landing_page_returns_html(frontend_client: AsyncClient) -> None:
    response = await frontend_client.get("/agent")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    text = response.text
    assert "<!DOCTYPE html>" in text
    assert "/static/frontend/index.js" in text


@pytest.mark.asyncio
async def test_agent_login_anonymous(frontend_client: AsyncClient) -> None:
    response = await frontend_client.get(
        f"{AGENT_API_PREFIX}/login",
        params={"redirect": "humanitec://auth/callback"},
    )
    assert response.status_code == 200
    text = response.text
    assert "Войти через Humanitec" in text
    assert "humanitec%3A%2F%2Fauth%2Fcallback" in text


@pytest.mark.asyncio
async def test_agent_login_authenticated(
    frontend_client_with_auth: AsyncClient,
    auth_token: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    response = await frontend_client_with_auth.get(f"{AGENT_API_PREFIX}/login")
    assert response.status_code == 200
    text = response.text
    assert token_data.email in text or "пользователь" in text
    assert "/frontend/api/agent/auth/device-token" in text


@pytest.mark.asyncio
async def test_device_token_unauthorized(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(f"{AGENT_API_PREFIX}/auth/device-token")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_issue_device_token_no_active_company(
    frontend_client: AsyncClient,
    frontend_container,
) -> None:
    user_id = f"agent_no_co_{uuid.uuid4().hex[:10]}"
    user = User(
        user_id=user_id,
        name="No Company User",
        emails=[f"{user_id}@test.local"],
        companies={},
        active_company_id="",
    )
    await frontend_container.user_repository.set(user)
    token = get_token_service().create_token(user_id, company_id="", roles=[])
    frontend_client.cookies.set("auth_token", token)
    response = await frontend_client.post(f"{AGENT_API_PREFIX}/auth/device-token")
    assert response.status_code == 400
    assert response.json()["detail"] == "Компания не выбрана"


@pytest.mark.asyncio
async def test_device_token_success(
    frontend_client_with_auth: AsyncClient,
    auth_token: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    response = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/auth/device-token")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["token"], str)

    device_token_data = get_token_service().validate_token(body["token"])
    assert device_token_data is not None
    assert device_token_data.user_id == token_data.user_id
    assert device_token_data.company_id == token_data.company_id
    assert device_token_data.metadata.get("token_purpose") == "device"


@pytest.mark.asyncio
async def test_create_pairing_code(
    frontend_client_with_auth: AsyncClient,
    auth_token: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    response = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert response.status_code == 200
    body = response.json()
    assert len(body["pairing_code"]) == 6
    assert body["expires_in_seconds"] >= 60


@pytest.mark.asyncio
async def test_register_invalid_pairing_code(frontend_client: AsyncClient, unique_id: str) -> None:
    response = await frontend_client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": "000000",
            "device_id": f"device-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Недействительный или истёкший pairing code"


@pytest.mark.asyncio
async def test_register_invalid_json(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        f"{AGENT_API_PREFIX}/register",
        content="not-json",
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_device_id(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": "123456",
            "device_name": "Test",
            "os": "darwin",
            "hostname": "host",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_wrong_pairing_code_length(frontend_client: AsyncClient, unique_id: str) -> None:
    response = await frontend_client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": "12345",
            "device_id": f"device-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_corrupted_pairing_data(
    frontend_client: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    pairing_code = "111111"
    key = f"{PAIRING_CODE_PREFIX}{pairing_code}"
    await frontend_container.shared_storage.set(key, json.dumps("not-json"), force_global=True)
    try:
        response = await frontend_client.post(
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
        assert response.json()["detail"] == "Повреждённые данные pairing code"
    finally:
        await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_register_success(
    frontend_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    pairing_code = "222222"
    device_id = f"device-{unique_id}"
    pairing_key = f"{PAIRING_CODE_PREFIX}{pairing_code}"
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"

    await _seed_agent_pairing(
        frontend_container,
        pairing_code=pairing_code,
        user_id=token_data.user_id,
        company_id=token_data.company_id,
    )
    try:
        response = await frontend_client.post(
            f"{AGENT_API_PREFIX}/register",
            json={
                "pairing_code": pairing_code,
                "device_id": device_id,
                "device_name": f"Device {unique_id}",
                "os": "darwin",
                "hostname": f"host-{unique_id}",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["device_id"] == device_id
        assert isinstance(body["token"], str)
        assert body["platform_mcp_url"] == (
            f"{get_frontend_public_base_url()}/flows/api/v1/agent/platform-mcp"
        )
        assert body["frontend_base_url"] == get_frontend_public_base_url()
        assert body["tunnel_ws_url"] == "ws://system.lvh.me:9004/frontend/api/agent/tunnel"
        assert body["company_id"] == token_data.company_id

        stored_raw = await frontend_container.shared_storage.get(device_key, force_global=True)
        assert stored_raw is not None
        device = AgentDeviceRecord.model_validate_json(stored_raw)
        assert device.device_id == device_id
        assert device.user_id == token_data.user_id
        assert device.company_id == token_data.company_id
        assert device.policy.shell_enabled is False

        pairing_left = await frontend_container.shared_storage.get(pairing_key, force_global=True)
        assert pairing_left is None
    finally:
        await frontend_container.shared_storage.delete(pairing_key, force_global=True)
        await frontend_container.shared_storage.delete(device_key, force_global=True)


@pytest.mark.asyncio
async def test_register_pairing_code_single_use(
    frontend_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    pairing_code = "333333"
    device_key = f"{DEVICE_KEY_PREFIX}device-reuse-{unique_id}"
    pairing_key = f"{PAIRING_CODE_PREFIX}{pairing_code}"

    await _seed_agent_pairing(
        frontend_container,
        pairing_code=pairing_code,
        user_id=token_data.user_id,
        company_id=token_data.company_id,
    )
    payload = {
        "pairing_code": pairing_code,
        "device_id": f"device-reuse-{unique_id}",
        "device_name": f"Device {unique_id}",
        "os": "linux",
        "hostname": f"host-{unique_id}",
    }
    try:
        first = await frontend_client.post(f"{AGENT_API_PREFIX}/register", json=payload)
        assert first.status_code == 200
        second = await frontend_client.post(f"{AGENT_API_PREFIX}/register", json=payload)
        assert second.status_code == 400
    finally:
        await frontend_container.shared_storage.delete(pairing_key, force_global=True)
        await frontend_container.shared_storage.delete(device_key, force_global=True)


@pytest.mark.asyncio
async def test_list_devices_after_register(
    frontend_client_with_auth: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    pairing_code = "444444"
    device_id = f"device-list-{unique_id}"
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    pairing_key = f"{PAIRING_CODE_PREFIX}{pairing_code}"

    await _seed_agent_pairing(
        frontend_container,
        pairing_code=pairing_code,
        user_id=token_data.user_id,
        company_id=token_data.company_id,
    )
    try:
        register_response = await frontend_client_with_auth.post(
            f"{AGENT_API_PREFIX}/register",
            json={
                "pairing_code": pairing_code,
                "device_id": device_id,
                "device_name": f"Listed {unique_id}",
                "os": "win32",
                "hostname": f"pc-{unique_id}",
            },
        )
        assert register_response.status_code == 200

        list_response = await frontend_client_with_auth.get(f"{AGENT_API_PREFIX}/devices")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        device_ids = [item["device_id"] for item in items]
        assert device_id in device_ids
    finally:
        await frontend_container.shared_storage.delete(pairing_key, force_global=True)
        await frontend_container.shared_storage.delete(device_key, force_global=True)


@pytest.mark.asyncio
async def test_agent_discover(
    frontend_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from pathlib import Path

    from apps.agent.config import reset_agent_settings
    from tests.agent.fixtures.local_releases import require_local_release_asset_name

    reset_agent_settings()
    _ = require_local_release_asset_name(Path(agent_local_release_artifact))
    response = await frontend_client.get(f"{AGENT_API_PREFIX}/discover")
    assert response.status_code == 200
    body = response.json()
    assert body["frontend_base_url"] == get_frontend_public_base_url()
    assert body["releases"]["ready"] is True


@pytest.mark.asyncio
async def test_download_unknown_platform(frontend_client: AsyncClient) -> None:
    response = await frontend_client.get(
        f"{AGENT_API_PREFIX}/download/haiku",
        follow_redirects=False,
    )
    assert response.status_code == 400
    body = response.json()
    assert "Неподдерживаемая платформа" in body["detail"]


@pytest.mark.asyncio
async def test_revoke_blocks_tunnel_reconnect(
    frontend_client_with_auth: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    from apps.agent.service import TOKEN_DENY_PREFIX
    from apps.agent.tunnel import agent_tunnel_websocket

    pairing_response = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing_response.status_code == 200
    pairing_code = pairing_response.json()["pairing_code"]
    device_id = f"device-revoke-tunnel-{unique_id}"

    register_response = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": f"Revoke tunnel {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register_response.status_code == 200
    device_token = register_response.json()["token"]

    revoke_response = await frontend_client_with_auth.delete(
        f"{AGENT_API_PREFIX}/devices/{device_id}",
    )
    assert revoke_response.status_code == 204

    class _RejectedWebSocket:
        def __init__(self) -> None:
            self.accepted = False
            self.close_code: int | None = None

        async def accept(self) -> None:
            self.accepted = True

        async def receive_text(self) -> str:
            raise WebSocketDisconnect()

        async def send_text(self, data: str) -> None:
            return None

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.close_code = code

    tunnel_socket = _RejectedWebSocket()
    await agent_tunnel_websocket(
        tunnel_socket,
        frontend_container,
        token=device_token,
    )
    assert tunnel_socket.accepted is True
    assert tunnel_socket.close_code in {4401, 4403}

    deny_raw = await frontend_container.shared_storage.get(
        f"{TOKEN_DENY_PREFIX}{device_id}",
        force_global=True,
    )
    assert deny_raw is not None


@pytest.mark.asyncio
async def test_update_device_policy(
    frontend_client_with_auth: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    pairing_code = "666666"
    device_id = f"device-policy-{unique_id}"
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    pairing_key = f"{PAIRING_CODE_PREFIX}{pairing_code}"

    await _seed_agent_pairing(
        frontend_container,
        pairing_code=pairing_code,
        user_id=token_data.user_id,
        company_id=token_data.company_id,
    )
    try:
        register_response = await frontend_client_with_auth.post(
            f"{AGENT_API_PREFIX}/register",
            json={
                "pairing_code": pairing_code,
                "device_id": device_id,
                "device_name": f"Policy {unique_id}",
                "os": "darwin",
                "hostname": f"host-{unique_id}",
            },
        )
        assert register_response.status_code == 200

        patch_response = await frontend_client_with_auth.patch(
            f"{AGENT_API_PREFIX}/devices/{device_id}/policy",
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
        assert patch_response.status_code == 200
        body = patch_response.json()
        assert body["policy"]["shell_enabled"] is True

        stored_raw = await frontend_container.shared_storage.get(device_key, force_global=True)
        assert stored_raw is not None
        device = AgentDeviceRecord.model_validate_json(stored_raw)
        assert device.policy.shell_enabled is True
    finally:
        await frontend_container.shared_storage.delete(pairing_key, force_global=True)
        await frontend_container.shared_storage.delete(device_key, force_global=True)


@pytest.mark.asyncio
async def test_download_redirect_resolves_asset(
    frontend_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from pathlib import Path

    from apps.agent.config import reset_agent_settings
    from scripts.agent_build import detect_host_platform
    from tests.agent.fixtures.local_releases import require_local_release_asset_name

    reset_agent_settings()
    asset_name = require_local_release_asset_name(Path(agent_local_release_artifact))
    platform_name = detect_host_platform()
    response = await frontend_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert "/releases/artifact/" in location
    assert asset_name in location or platform_name in location


@pytest.mark.asyncio
async def test_releases_status_ready(
    frontend_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from pathlib import Path

    from apps.agent.config import reset_agent_settings
    from tests.agent.fixtures.local_releases import require_local_release_asset_name

    reset_agent_settings()
    _ = require_local_release_asset_name(Path(agent_local_release_artifact))
    response = await frontend_client.get(f"{AGENT_API_PREFIX}/releases/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_download_redirect_serves_local_artifact(
    frontend_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from pathlib import Path

    from apps.agent.config import reset_agent_settings
    from scripts.agent_build import detect_host_platform
    from tests.agent.fixtures.local_releases import require_local_release_asset_name

    reset_agent_settings()
    artifact_path = Path(agent_local_release_artifact)
    _ = require_local_release_asset_name(artifact_path)
    platform_name = detect_host_platform()
    response = await frontend_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/octet-stream")
    assert len(response.content) >= artifact_path.stat().st_size // 2


@pytest.mark.asyncio
async def test_revoke_device(
    frontend_client_with_auth: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token)
    assert token_data is not None

    pairing_code = "555555"
    device_id = f"device-revoke-{unique_id}"
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    pairing_key = f"{PAIRING_CODE_PREFIX}{pairing_code}"

    await _seed_agent_pairing(
        frontend_container,
        pairing_code=pairing_code,
        user_id=token_data.user_id,
        company_id=token_data.company_id,
    )
    try:
        register_response = await frontend_client_with_auth.post(
            f"{AGENT_API_PREFIX}/register",
            json={
                "pairing_code": pairing_code,
                "device_id": device_id,
                "device_name": f"Revoke {unique_id}",
                "os": "darwin",
                "hostname": f"host-{unique_id}",
            },
        )
        assert register_response.status_code == 200

        revoke_response = await frontend_client_with_auth.delete(
            f"{AGENT_API_PREFIX}/devices/{device_id}",
        )
        assert revoke_response.status_code == 204

        stored_raw = await frontend_container.shared_storage.get(device_key, force_global=True)
        assert stored_raw is not None
        device = AgentDeviceRecord.model_validate_json(stored_raw)
        assert device.is_active is False
    finally:
        await frontend_container.shared_storage.delete(pairing_key, force_global=True)
        await frontend_container.shared_storage.delete(device_key, force_global=True)


@pytest.mark.asyncio
async def test_agent_tunnel_ping_pong(
    frontend_client_with_auth: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    from apps.agent.tunnel import agent_tunnel_websocket

    device_id = f"device-tunnel-{unique_id}"

    pairing_response = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing_response.status_code == 200
    pairing_code = pairing_response.json()["pairing_code"]

    register_response = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": f"Tunnel {unique_id}",
            "os": "darwin",
            "hostname": f"tunnel-{unique_id}",
        },
    )
    assert register_response.status_code == 200
    device_token = register_response.json()["token"]

    class _TunnelWebSocket:
        def __init__(self) -> None:
            self.incoming = [json.dumps({"type": "ping"})]
            self.outgoing: list[str] = []

        async def accept(self) -> None:
            return None

        async def receive_text(self) -> str:
            if not self.incoming:
                raise WebSocketDisconnect()
            return self.incoming.pop(0)

        async def send_text(self, data: str) -> None:
            self.outgoing.append(data)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            raise WebSocketDisconnect()

    tunnel_socket = _TunnelWebSocket()
    await agent_tunnel_websocket(
        tunnel_socket,
        frontend_container,
        token=device_token,
    )

    assert len(tunnel_socket.outgoing) == 2
    policy_payload = json.loads(tunnel_socket.outgoing[0])
    assert policy_payload["type"] == "policy"
    assert isinstance(policy_payload.get("policy"), dict)
    pong_payload = json.loads(tunnel_socket.outgoing[1])
    assert pong_payload["type"] == "pong"
    assert pong_payload["device_id"] == device_id
