"""HTTP control-plane for Flow UI live shares (real DB + short links)."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

from apps.flows.src.container import get_container
from core.utils.tokens import TokenType, get_token_service
from tests.flows._flow_ui_session import (
    bootstrap_flow_ui_session,
    load_flow_ui_state,
    sync_flow_ui_session,
)
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow

_SHARE_HOST_HEADERS = {"Host": "linnex.io"}
_SHARE_EXCHANGE_HEADERS = {"Host": "linnex.io", "Origin": "http://linnex.io"}


def _code_from_share_url(share_url: str) -> str:
    if "/l/" not in share_url:
        raise AssertionError(f"expected /l/ in share_url: {share_url}")
    return share_url.rstrip("/").split("/l/")[-1]


def _token_user_id(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("auth token must validate")
    return token_data.user_id


@pytest.mark.asyncio
async def test_flow_ui_shares_create_list_exchange_revoke_and_short_link(
    client: AsyncClient,
    frontend_app,
    app: object,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = app
    owner_user_id = _token_user_id(auth_token_system)
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-api-{unique_id}",
        context_id=f"ctx-api-{unique_id}",
        user_id=owner_user_id,
    )
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=bootstrapped.state.ui_document.revision,
        message_value=f"draft-before-share-{unique_id}",
        user_id=owner_user_id,
    )
    assert synced.state.ui_document.revision == 2

    stale = await client.post(
        "/flows/api/v1/flow-ui/shares",
        headers=_SHARE_HOST_HEADERS,
        json={
            "flow_id": flow_id,
            "context_id": context_id,
            "document_id": f"flow-ui:{context_id}",
            "minimum_revision": 1,
            "permission": "viewer",
            "expires_in_seconds": 300,
        },
    )
    assert stale.status_code == 409, stale.text

    created = await client.post(
        "/flows/api/v1/flow-ui/shares",
        headers=_SHARE_HOST_HEADERS,
        json={
            "flow_id": flow_id,
            "context_id": context_id,
            "document_id": f"flow-ui:{context_id}",
            "minimum_revision": 2,
            "permission": "viewer",
            "expires_in_seconds": 300,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    grant = body["grant"]
    share_url = body["share_url"]
    grant_id = grant["grant_id"]
    assert grant["permission"] == "viewer"
    assert grant["minimum_revision"] == 2
    assert grant["context_id"] == context_id
    assert "/l/" in share_url

    listed = await client.get(
        "/flows/api/v1/flow-ui/shares",
        params={"flow_id": flow_id, "context_id": context_id},
    )
    assert listed.status_code == 200, listed.text
    assert [item["grant_id"] for item in listed.json()] == [grant_id]

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
    assert token_payload["context_id"] == context_id
    assert token_payload["document_id"] == f"flow-ui:{context_id}"
    assert token_payload["minimum_revision"] == 2
    token_data = get_token_service().validate_token(token_payload["token"])
    assert token_data is not None
    assert token_data.token_type == TokenType.FLOW_UI_SHARE
    assert token_data.metadata["flow_ui_share_grant_id"] == grant_id

    durable = await load_flow_ui_state(session_id)
    assert durable.ui_document.surfaces["main"].data_model.values["message"] == (
        f"draft-before-share-{unique_id}"
    )

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
        assert "shared_session" in page.text
        assert grant_id in page.text
        assert 'href="/static/core/assets/css/tokens.css"' in page.text
        assert 'id="theme-toggle"' in page.text
        assert 'surface.theme = \'auto\'' in page.text
        assert 'data-theme="light"' in page.text

    revoked = await client.delete(f"/flows/api/v1/flow-ui/shares/{grant_id}")
    assert revoked.status_code == 204, revoked.text

    listed_after = await client.get(
        "/flows/api/v1/flow-ui/shares",
        params={"flow_id": flow_id, "context_id": context_id},
    )
    assert listed_after.status_code == 200
    assert listed_after.json()[0]["revoked_at"] is not None

    blocked = await client.post(
        f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
        headers=_SHARE_EXCHANGE_HEADERS,
    )
    assert blocked.status_code == 404, blocked.text

    missing = await client.delete(f"/flows/api/v1/flow-ui/shares/{grant_id}")
    assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_flow_ui_share_interact_grant_authorizes_mutations(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = app
    owner_user_id = _token_user_id(auth_token_system)
    token_data = get_token_service().validate_token(auth_token_system)
    if token_data is None:
        raise AssertionError("auth token must validate")
    company_id = token_data.company_id
    flow_id, context_id, _, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-interact-{unique_id}",
        context_id=f"ctx-interact-{unique_id}",
        user_id=owner_user_id,
    )
    created = await client.post(
        "/flows/api/v1/flow-ui/shares",
        headers=_SHARE_HOST_HEADERS,
        json={
            "flow_id": flow_id,
            "context_id": context_id,
            "document_id": f"flow-ui:{context_id}",
            "minimum_revision": bootstrapped.state.ui_document.revision,
            "permission": "editor",
            "expires_in_seconds": 300,
        },
    )
    assert created.status_code == 200, created.text
    grant_id = created.json()["grant"]["grant_id"]
    grant = await get_container().flow_ui_share_service.authorize(
        grant_id=grant_id,
        company_id=company_id,
        flow_id=flow_id,
        context_id=context_id,
        require_editor=True,
    )
    assert grant.permission == "editor"


@pytest.mark.asyncio
async def test_flow_ui_share_token_interface_profile_is_read_only_for_view(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = app
    owner_user_id = _token_user_id(auth_token_system)
    flow_id = f"share_profile_{unique_id}"
    context_id = f"ctx-profile-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        bootstrapped = (
            await bootstrap_flow_ui_session(
                flow_id=flow_id,
                context_id=context_id,
                user_id=owner_user_id,
            )
        )[3]
        created = await client.post(
            "/flows/api/v1/flow-ui/shares",
            headers=_SHARE_HOST_HEADERS,
            json={
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": bootstrapped.state.ui_document.revision,
                "permission": "viewer",
                "expires_in_seconds": 300,
            },
        )
        assert created.status_code == 200, created.text
        grant_id = created.json()["grant"]["grant_id"]
        exchanged = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
            headers=_SHARE_EXCHANGE_HEADERS,
        )
        assert exchanged.status_code == 200, exchanged.text
        share_token = exchanged.json()["token"]

        profile = await client.get(
            f"/flows/api/v1/{flow_id}/interface-profile",
            headers={
                "Host": "linnex.io",
                "Origin": "http://linnex.io",
                "Authorization": f"Bearer {share_token}",
            },
        )
        assert profile.status_code == 200, profile.text
        body = profile.json()
        assert body["viewer"] == {
            "can_edit_flow": False,
            "can_interact": False,
            "can_share": False,
            "auth_mode": "share",
        }
        assert body["capabilities"]["autosync"] is False
        assert body["capabilities"]["cancel"] is False
        assert body["capabilities"]["files"] is False
        assert "document" not in body
        assert "values" not in body
        assert "artifacts" not in body

        interact = await client.post(
            "/flows/api/v1/flow-ui/shares",
            headers=_SHARE_HOST_HEADERS,
            json={
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": bootstrapped.state.ui_document.revision,
                "permission": "editor",
                "expires_in_seconds": 300,
            },
        )
        assert interact.status_code == 200, interact.text
        interact_grant_id = interact.json()["grant"]["grant_id"]
        interact_exchanged = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{interact_grant_id}",
            headers=_SHARE_EXCHANGE_HEADERS,
        )
        assert interact_exchanged.status_code == 200, interact_exchanged.text
        interact_token = interact_exchanged.json()["token"]
        interact_profile = await client.get(
            f"/flows/api/v1/{flow_id}/interface-profile",
            headers={
                "Host": "linnex.io",
                "Origin": "http://linnex.io",
                "Authorization": f"Bearer {interact_token}",
            },
        )
        assert interact_profile.status_code == 200, interact_profile.text
        interact_body = interact_profile.json()
        assert interact_body["viewer"]["can_interact"] is True
        assert interact_body["viewer"]["can_edit_flow"] is False
        assert interact_body["viewer"]["can_share"] is False
        assert interact_body["viewer"]["auth_mode"] == "share"
        assert interact_body["capabilities"]["autosync"] is True
        assert interact_body["capabilities"]["files"] is False
    finally:
        await delete_flow(client, flow_id)
