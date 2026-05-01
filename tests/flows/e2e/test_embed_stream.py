"""E2E проверки канонического embed-пути: short-lived embed-session token + A2A."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.context import Context, clear_context, set_context
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


@pytest_asyncio.fixture
async def embed_test_auth(frontend_container, unique_id):
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import FlowConfig

    company_id = f"test_company_{unique_id}"
    company = Company(company_id=company_id, name="Test Company", owner_id="test_user")
    await frontend_container.company_repository.set(company)

    user_id = f"test_user_{unique_id}"
    user = User(
        user_id=user_id,
        name="Test User",
        email=f"{user_id}@test.com",
        companies={company_id: ["admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    company.members = {user_id: ["admin"]}
    await frontend_container.company_repository.set(company)

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    flows_container = get_container()
    flow_id = f"test_agent_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Test Agent",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": (
                    "async def run(state):\n"
                    "    user_text = state.get('content', '')\n"
                    "    state['response'] = f'embed-ok:{user_text}'\n"
                    "    return state"
                ),
            }
        },
        edges=[{"from": "main", "to": None}],
    )
    await flows_container.flow_repository.set(agent)
    clear_context()

    token = get_token_service().create_token(user_id, company_id=company_id)
    yield {"Authorization": f"Bearer {token}"}, flow_id, company_id, user_id

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    await flows_container.flow_repository.delete(flow_id)
    clear_context()


async def _create_embed(frontend_client: AsyncClient, auth_headers: dict, flow_id: str) -> str:
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Embed E2E",
            "flow_id": flow_id,
            "allowed_origins": ["https://larashved.ru"],
        },
    )
    assert response.status_code == 200
    return response.json()["embed_id"]


@pytest.mark.asyncio
async def test_embed_session_token_streams_via_a2a(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": f"test-stream-{unique_id}",
        "method": "message/stream",
        "params": {
            "message": {
                "messageId": f"m1-{unique_id}",
                "role": "user",
                "parts": [{"kind": "text", "text": f"Привет-{unique_id}"}],
            }
        },
    }
    stream_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json=rpc_body,
        timeout=30.0,
    )
    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert "data:" in stream_response.text
    assert "\"jsonrpc\": \"2.0\"" in stream_response.text
    assert "embed-ok:" in stream_response.text

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_streams_via_a2a_with_hum_api_key(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)

    api_key_response = await frontend_client.post(
        "/frontend/api/api-keys",
        headers=auth_headers,
        json={"name": f"Embed hum key {unique_id}", "scopes": ["agents:read"]},
    )
    assert api_key_response.status_code == 200
    hum_api_key = api_key_response.json()["secret"]
    assert hum_api_key.startswith("hum_")

    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers={"Authorization": f"Bearer {hum_api_key}"},
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": f"test-stream-hum-{unique_id}",
        "method": "message/stream",
        "params": {
            "message": {
                "messageId": f"m-hum-{unique_id}",
                "role": "user",
                "parts": [{"kind": "text", "text": f"Привет-hum-{unique_id}"}],
            }
        },
    }
    stream_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json=rpc_body,
        timeout=30.0,
    )
    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert "data:" in stream_response.text
    assert "embed-ok:" in stream_response.text

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_wrong_origin(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": f"test-origin-{unique_id}",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"m2-{unique_id}",
                "role": "user",
                "parts": [{"kind": "text", "text": "Привет"}],
            }
        },
    }
    deny_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://evil.example",
        },
        json=rpc_body,
    )
    assert deny_response.status_code == 403

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_wrong_embed_id(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": f"test-embed-mismatch-{unique_id}",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"m-embed-mismatch-{unique_id}",
                "role": "user",
                "parts": [{"kind": "text", "text": "Привет"}],
            }
        },
    }
    deny_response = await flows_client.post(
        f"/flows/api/v1/embed/{other_embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json=rpc_body,
    )
    assert deny_response.status_code == 200
    deny_payload = deny_response.json()
    assert deny_payload["error"]["code"] == -32000
    assert "not allowed for this embed" in deny_payload["error"]["message"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)
    await frontend_client.delete(f"/frontend/api/embed/configs/{other_embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_wrong_branch(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": f"test-skill-{unique_id}",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"m-skill-{unique_id}",
                "role": "user",
                "parts": [{"kind": "text", "text": "Привет"}],
            },
            "metadata": {"branch": "non_embed_allowed_branch"},
        },
    }
    deny_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json=rpc_body,
    )
    assert deny_response.status_code == 200
    deny_payload = deny_response.json()
    assert deny_payload["error"]["code"] == -32000
    assert "not allowed for this branch" in deny_payload["error"]["message"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_forbidden_method(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]

    rpc_body = {
        "jsonrpc": "2.0",
        "id": "test-forbidden-method",
        "method": "tasks/get",
        "params": {"id": "t1"},
    }
    deny_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json=rpc_body,
    )
    assert deny_response.status_code == 200
    deny_payload = deny_response.json()
    assert deny_payload["error"]["code"] == -32000
    assert "supports only message/send and message/stream" in deny_payload["error"]["message"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_contains_expected_claims(
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    payload = token_response.json()
    token = payload["token"]
    token_data = get_token_service().validate_token(token)
    assert token_data is not None
    assert token_data.user_id == user_id
    assert token_data.company_id == company_id
    assert token_data.token_type.value == "embed_session"
    assert token_data.metadata["embed_id"] == embed_id
    assert token_data.metadata["embed_flow_id"] == flow_id
    assert token_data.metadata["embed_branch_id"] == "default"
    assert token_data.metadata["allowed_origin"] == "https://larashved.ru"
    assert token_data.exp > datetime.now(timezone.utc)

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_requires_origin_when_origins_limited(
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"expires_in_seconds": 300},
    )
    assert response.status_code == 400
    assert "origin обязателен" in response.json()["detail"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_route_preflight_allows_configured_origin(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)

    response = await flows_client.options(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Origin": "https://larashved.ru",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "https://larashved.ru"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_route_preflight_denies_unconfigured_origin(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)

    response = await flows_client.options(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 403

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_legacy_embed_route_removed(flows_client: AsyncClient):
    response = await flows_client.get("/flows/api/v1/embed/some-widget/settings")
    assert response.status_code == 401

