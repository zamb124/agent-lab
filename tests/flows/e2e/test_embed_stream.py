"""E2E проверки канонического embed-пути: short-lived embed-session token + A2A."""

from datetime import datetime, timezone

import pytest
from httpx2 import AsyncClient

from core.models.identity_models import Company
from core.utils.tokens import get_token_service
from tests.flows._a2a_v1 import A2A_HEADERS
from tests.flows._flow_ui_session import ui_action_message


async def _create_embed(
    frontend_client: AsyncClient, auth_headers: dict[str, str], flow_id: str
) -> str:
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
        "method": "SendStreamingMessage",
        "params": {
            "message": {
                "messageId": f"m1-{unique_id}",
                "role": "ROLE_USER",
                "parts": [{"text": f"Привет-{unique_id}"}],
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
    assert '"jsonrpc": "2.0"' in stream_response.text
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
        "method": "SendStreamingMessage",
        "params": {
            "message": {
                "messageId": f"m-hum-{unique_id}",
                "role": "ROLE_USER",
                "parts": [{"text": f"Привет-hum-{unique_id}"}],
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
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"m2-{unique_id}",
                "role": "ROLE_USER",
                "parts": [{"text": "Привет"}],
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
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"m-embed-mismatch-{unique_id}",
                "role": "ROLE_USER",
                "parts": [{"text": "Привет"}],
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
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{other_embed_id}", headers=auth_headers
    )


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
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": f"m-skill-{unique_id}",
                "role": "ROLE_USER",
                "parts": [{"text": "Привет"}],
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
        "method": "CreateTaskPushNotificationConfig",
        "params": {
            "taskId": "t1",
            "pushNotificationConfig": {
                "id": "cfg-1",
                "url": "https://example.com/push",
            },
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
    assert "cannot access this A2A method" in deny_payload["error"]["message"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_list_tasks_without_context_id(
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

    deny_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json={
            "jsonrpc": "2.0",
            "id": f"test-list-no-ctx-{unique_id}",
            "method": "ListTasks",
            "params": {"pageSize": 50, "includeArtifacts": True},
        },
    )
    assert deny_response.status_code == 200
    deny_payload = deny_response.json()
    assert deny_payload["error"]["code"] == -32000
    assert "ListTasks requires contextId" in deny_payload["error"]["message"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_allows_list_tasks_with_context_id(
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
    context_id = f"ctx-embed-list-{unique_id}"

    list_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
        json={
            "jsonrpc": "2.0",
            "id": f"test-list-ctx-{unique_id}",
            "method": "ListTasks",
            "params": {
                "contextId": context_id,
                "pageSize": 50,
                "includeArtifacts": True,
            },
        },
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert "error" not in list_payload, list_payload
    result = list_payload["result"]
    assert isinstance(result, dict)
    tasks = result.get("tasks", [])
    assert isinstance(tasks, list)
    assert tasks == []
    assert result.get("nextPageToken", "") == ""

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_interface_then_ui_action_then_list_tasks(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    """Embed-клиент: GET /interface, затем ui-action ход и ListTasks по context — без allowlist-отказов."""
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    embed_token = token_response.json()["token"]
    context_id = f"ctx-embed-action-{unique_id}"
    embed_headers = {
        **A2A_HEADERS,
        "Authorization": f"Bearer {embed_token}",
        "Origin": "https://larashved.ru",
    }

    interface_response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface", headers=embed_headers
    )
    assert interface_response.status_code == 200, interface_response.text
    interface_payload = interface_response.json()
    assert interface_payload["flow_id"] == flow_id
    assert interface_payload["viewer"]["auth_mode"] == "embed"
    assert interface_payload["document"]["start_page_id"]

    action_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers=embed_headers,
        json={
            "jsonrpc": "2.0",
            "id": f"test-action-{unique_id}",
            "method": "SendMessage",
            "params": {
                "message": ui_action_message(
                    context_id=context_id,
                    action="send",
                    source="conversation",
                    payload={"text": "hello from embed"},
                ),
                "metadata": {"branch": "default"},
            },
        },
        timeout=30.0,
    )
    assert action_response.status_code == 200
    action_payload = action_response.json()
    assert "error" not in action_payload, action_payload
    assert action_payload["result"]["contextId"] == context_id

    list_response = await flows_client.post(
        f"/flows/api/v1/embed/{embed_id}",
        headers=embed_headers,
        json={
            "jsonrpc": "2.0",
            "id": f"test-hydrate-{unique_id}",
            "method": "ListTasks",
            "params": {
                "contextId": context_id,
                "pageSize": 50,
                "includeArtifacts": True,
            },
        },
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert "error" not in list_payload, list_payload
    result = list_payload["result"]
    assert isinstance(result, dict)
    tasks = result.get("tasks", [])
    assert isinstance(tasks, list)
    assert [task["contextId"] for task in tasks] == [context_id]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_allows_tasks_cancel(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    di,
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
    task_id = f"missing-embed-cancel-{unique_id}"

    try:
        cancel_response = await flows_client.post(
            f"/flows/api/v1/embed/{embed_id}",
            headers={
                "Authorization": f"Bearer {embed_token}",
                "Origin": "https://larashved.ru",
            },
            json={
                "jsonrpc": "2.0",
                "id": f"test-cancel-{unique_id}",
                "method": "CancelTask",
                "params": {"id": task_id},
            },
        )
        assert cancel_response.status_code == 200
        cancel_payload = cancel_response.json()
        assert cancel_payload["error"]["code"] == -32001
        assert cancel_payload["error"]["message"] == "TaskNotFoundError"
    finally:
        await di.redis_client.delete(f"cancel:{task_id}")

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_session_token_rejects_company_mismatch(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    frontend_di,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, company_id, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_company_id = f"other_embed_company_{unique_id}"
    await Company.set(
        Company(
            company_id=other_company_id,
            name="Other Embed Company",
            owner_user_id=f"other_owner_{unique_id}",
        )
    )
    embed_token = get_token_service().create_embed_session_token(
        user_id=f"embed_guest_{unique_id}",
        company_id=other_company_id,
        roles=["guest"],
        expires_in=300,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "embed_branch_id": "default",
            "allowed_origin": "https://larashved.ru",
            "issued_by": "test.company_mismatch",
        },
    )

    try:
        deny_response = await flows_client.post(
            f"/flows/api/v1/embed/{embed_id}",
            headers={
                "Authorization": f"Bearer {embed_token}",
                "Origin": "https://larashved.ru",
            },
            json={
                "jsonrpc": "2.0",
                "id": f"test-company-mismatch-{unique_id}",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": f"m-company-mismatch-{unique_id}",
                        "role": "ROLE_USER",
                        "parts": [{"text": "Привет"}],
                    }
                },
            },
        )
        assert deny_response.status_code == 200
        deny_payload = deny_response.json()
        assert deny_payload["error"]["code"] == -32000
        assert "not allowed for this company" in deny_payload["error"]["message"]
        assert company_id != other_company_id
    finally:
        await Company.delete_by_id(other_company_id)
        await frontend_client.delete(
            f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
        )


@pytest.mark.asyncio
async def test_embed_session_token_rejects_missing_branch_claim(
    flows_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth,
    unique_id,
):
    auth_headers, flow_id, company_id, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = get_token_service().create_embed_session_token(
        user_id=f"embed_guest_no_branch_{unique_id}",
        company_id=company_id,
        roles=["guest"],
        expires_in=300,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "allowed_origin": "https://larashved.ru",
            "issued_by": "test.missing_branch",
        },
    )

    try:
        deny_response = await flows_client.post(
            f"/flows/api/v1/embed/{embed_id}",
            headers={
                "Authorization": f"Bearer {embed_token}",
                "Origin": "https://larashved.ru",
            },
            json={
                "jsonrpc": "2.0",
                "id": f"test-missing-branch-{unique_id}",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": f"m-missing-branch-{unique_id}",
                        "role": "ROLE_USER",
                        "parts": [{"text": "Привет"}],
                    }
                },
            },
        )
        assert deny_response.status_code == 200
        deny_payload = deny_response.json()
        assert deny_payload["error"]["code"] == -32000
        assert "embed_branch_id is required" in deny_payload["error"]["message"]
    finally:
        await frontend_client.delete(
            f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
        )


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
    assert "origin is required" in response.json()["detail"]

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
            "Access-Control-Request-Headers": (
                "authorization,content-type,x-platform-namespace,a2a-version,accept"
            ),
        },
    )
    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "https://larashved.ru"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    allow_headers = response.headers.get("Access-Control-Allow-Headers", "")
    assert "X-Platform-Namespace" in allow_headers
    assert "A2A-Version" in allow_headers
    assert "Accept" in allow_headers

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
