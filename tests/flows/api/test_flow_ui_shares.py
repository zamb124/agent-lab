"""HTTP control-plane живых share-ссылок на сессию flow (реальная БД + короткие ссылки)."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from httpx2 import ASGITransport, AsyncClient

from core.utils.tokens import TokenType, get_token_service
from tests.flows._flow_ui_session import a2a_send, text_message
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow

_SHARE_HOST_HEADERS = {"Host": "linnex.io"}
_SHARE_EXCHANGE_HEADERS = {"Host": "linnex.io", "Origin": "http://linnex.io"}
_SHARE_VIEW_HEADERS = {"Host": "linnex.io", "Origin": "http://linnex.io"}


def _code_from_share_url(share_url: str) -> str:
    if "/l/" not in share_url:
        raise AssertionError(f"expected /l/ in share_url: {share_url}")
    return share_url.rstrip("/").split("/l/")[-1]


def _token_scope(auth_token: str) -> tuple[str, str]:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("auth token must validate")
    return token_data.user_id, token_data.company_id


async def _start_session(client: AsyncClient, *, flow_id: str, context_id: str, text: str) -> None:
    task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text=text),
    )
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task


async def _create_share(
    client: AsyncClient,
    *,
    flow_id: str,
    context_id: str,
    permission: str,
    redacted_paths: list[str] | None = None,
) -> tuple[str, str]:
    created = await client.post(
        "/flows/api/v1/flow-ui/shares",
        headers=_SHARE_HOST_HEADERS,
        json={
            "flow_id": flow_id,
            "context_id": context_id,
            "permission": permission,
            "redacted_paths": redacted_paths or [],
            "expires_in_seconds": 300,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    return body["grant"]["grant_id"], body["share_url"]


async def _exchange(client: AsyncClient, grant_id: str) -> str:
    exchanged = await client.post(
        f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
        headers=_SHARE_EXCHANGE_HEADERS,
    )
    assert exchanged.status_code == 200, exchanged.text
    return exchanged.json()["token"]


@pytest.mark.asyncio
async def test_flow_ui_shares_create_list_exchange_revoke_and_short_link(
    client: AsyncClient,
    frontend_app,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id = f"share_api_{unique_id}"
    context_id = f"ctx-api-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        missing_session = await client.post(
            "/flows/api/v1/flow-ui/shares",
            headers=_SHARE_HOST_HEADERS,
            json={"flow_id": flow_id, "context_id": context_id, "permission": "viewer"},
        )
        assert missing_session.status_code == 409, missing_session.text
        assert missing_session.json()["error_code"] == "conflict"

        await _start_session(client, flow_id=flow_id, context_id=context_id, text="hello")
        grant_id, share_url = await _create_share(
            client,
            flow_id=flow_id,
            context_id=context_id,
            permission="viewer",
            redacted_paths=["/secret"],
        )
        assert "/l/" in share_url

        listed = await client.get(
            "/flows/api/v1/flow-ui/shares",
            params={"flow_id": flow_id, "context_id": context_id},
        )
        assert listed.status_code == 200, listed.text
        listed_items = listed.json()["items"]
        assert [item["grant_id"] for item in listed_items] == [grant_id]
        assert listed_items[0]["permission"] == "viewer"
        assert listed_items[0]["redacted_paths"] == ["/secret"]
        assert listed_items[0]["branch_id"] == "default"

        foreign_origin = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
            headers={"Host": "linnex.io", "Origin": "https://evil.example"},
        )
        assert foreign_origin.status_code == 403, foreign_origin.text

        exchanged = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
            headers=_SHARE_EXCHANGE_HEADERS,
        )
        assert exchanged.status_code == 200, exchanged.text
        token_payload = exchanged.json()
        assert token_payload["token_type"] == "Bearer"
        assert token_payload["permission"] == "viewer"
        assert token_payload["flow_id"] == flow_id
        assert token_payload["branch_id"] == "default"
        assert token_payload["context_id"] == context_id
        assert token_payload["redacted_paths"] == ["/secret"]
        token_data = get_token_service().validate_token(token_payload["token"])
        assert token_data is not None
        assert token_data.token_type == TokenType.FLOW_UI_SHARE
        assert token_data.metadata["flow_ui_share_grant_id"] == grant_id

        code = _code_from_share_url(share_url)
        transport = ASGITransport(app=frontend_app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
            headers={"Host": "testserver"},
        ) as frontend:
            redirect = await frontend.get(f"/l/{code}")
            assert redirect.status_code == 303, redirect.text
            location = redirect.headers.get("location")
            assert location is not None
            parsed = urlsplit(location)
            assert parsed.path == "/flow-session-share"
            assert f"grant={grant_id}" in (parsed.query or "")
            page = await frontend.get(f"/flow-session-share?grant={grant_id}")
            assert page.status_code == 200, page.text
            assert "platform-flow-ui" in page.text
            assert grant_id in page.text
            assert 'href="/static/core/assets/css/tokens.css"' in page.text

        revoked = await client.delete(f"/flows/api/v1/flow-ui/shares/{grant_id}")
        assert revoked.status_code == 200, revoked.text
        assert revoked.json() == {"status": "deleted", "grant_id": grant_id}

        listed_after = await client.get(
            "/flows/api/v1/flow-ui/shares",
            params={"flow_id": flow_id, "context_id": context_id},
        )
        assert listed_after.status_code == 200
        assert listed_after.json()["items"][0]["revoked_at"] is not None

        blocked = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
            headers=_SHARE_EXCHANGE_HEADERS,
        )
        assert blocked.status_code == 404, blocked.text

        missing = await client.delete(f"/flows/api/v1/flow-ui/shares/{grant_id}")
        assert missing.status_code == 404, missing.text
        assert missing.json()["error_code"] == "not_found"
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_flow_ui_share_editor_grant_authorizes_interaction(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
    di,
) -> None:
    _ = app
    _, company_id = _token_scope(auth_token_system)
    flow_id = f"share_editor_{unique_id}"
    context_id = f"ctx-editor-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _start_session(client, flow_id=flow_id, context_id=context_id, text="hello")
        grant_id, _ = await _create_share(
            client, flow_id=flow_id, context_id=context_id, permission="editor"
        )
        grant = await di.flow_ui_share_service.authorize(
            grant_id=grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
            require_editor=True,
        )
        assert grant.permission == "editor"

        viewer_grant_id, _ = await _create_share(
            client, flow_id=flow_id, context_id=context_id, permission="viewer"
        )
        with pytest.raises(PermissionError):
            _ = await di.flow_ui_share_service.authorize(
                grant_id=viewer_grant_id,
                company_id=company_id,
                flow_id=flow_id,
                context_id=context_id,
                require_editor=True,
            )
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_flow_ui_share_token_interface_follows_permission(
    client: AsyncClient,
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id = f"share_iface_{unique_id}"
    context_id = f"ctx-iface-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _start_session(client, flow_id=flow_id, context_id=context_id, text="hello")

        viewer_grant_id, _ = await _create_share(
            client, flow_id=flow_id, context_id=context_id, permission="viewer"
        )
        viewer_token = await _exchange(client, viewer_grant_id)
        viewer = await client.get(
            f"/flows/api/v1/{flow_id}/interface",
            headers={**_SHARE_VIEW_HEADERS, "Authorization": f"Bearer {viewer_token}"},
        )
        assert viewer.status_code == 200, viewer.text
        body = viewer.json()
        assert body["viewer"] == {
            "can_edit_flow": False,
            "can_interact": False,
            "can_share": False,
            "auth_mode": "share",
        }
        assert body["capabilities"] == {"cancel": False, "files": False, "voice": False}
        assert body["document"]["start_page_id"]
        assert body["flow_id"] == flow_id

        editor_grant_id, _ = await _create_share(
            client, flow_id=flow_id, context_id=context_id, permission="editor"
        )
        editor_token = await _exchange(client, editor_grant_id)
        editor = await client.get(
            f"/flows/api/v1/{flow_id}/interface",
            headers={**_SHARE_VIEW_HEADERS, "Authorization": f"Bearer {editor_token}"},
        )
        assert editor.status_code == 200, editor.text
        editor_body = editor.json()
        assert editor_body["viewer"]["can_interact"] is True
        assert editor_body["viewer"]["can_edit_flow"] is False
        assert editor_body["viewer"]["can_share"] is False
        assert editor_body["viewer"]["auth_mode"] == "share"
        assert editor_body["capabilities"]["cancel"] is True
        assert editor_body["capabilities"]["files"] is False

        other_branch = await client.get(
            f"/flows/api/v1/{flow_id}/interface",
            params={"branch_id": "other"},
            headers={**_SHARE_VIEW_HEADERS, "Authorization": f"Bearer {viewer_token}"},
        )
        assert other_branch.status_code == 403, other_branch.text
    finally:
        await delete_flow(client, flow_id)
