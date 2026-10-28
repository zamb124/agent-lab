"""FlowUIShareService поверх реального репозитория, workflow runtime и коротких ссылок."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from core.models.flow_ui_share import FlowUIShareCreateRequest, FlowUIShareGrant
from core.utils.tokens import TokenType, get_token_service
from tests.flows._flow_ui_session import (
    a2a_send,
    ensure_flow,
    load_flow_ui_state,
    text_message,
)


def _share_request(
    *,
    flow_id: str,
    context_id: str,
    permission: str = "viewer",
    redacted_paths: list[str] | None = None,
) -> FlowUIShareCreateRequest:
    return FlowUIShareCreateRequest.model_validate(
        {
            "flow_id": flow_id,
            "context_id": context_id,
            "permission": permission,
            "redacted_paths": redacted_paths or [],
            "expires_in_seconds": 300,
        }
    )


def _owner_scope(auth_token: str) -> tuple[str, str]:
    """(user_id, company_id) владельца сессии — того, от чьего имени ходит ``client``."""
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("auth token must validate")
    return token_data.user_id, token_data.company_id


async def _start_session(client: AsyncClient, di, *, flow_id: str, context_id: str) -> str:
    """Один текстовый ход создаёт durable-сессию; возвращает session_id."""
    _ = await ensure_flow(flow_id=flow_id, di=di)
    task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hello"),
    )
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task
    return f"{flow_id}:{context_id}"


@pytest.mark.asyncio
async def test_live_share_is_exact_scoped_revocable_and_read_only_by_default(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
    di,
) -> None:
    _ = app
    owner_user_id, company_id = _owner_scope(auth_token_system)
    flow_id = f"share-svc-{unique_id}"
    context_id = f"ctx-{unique_id}"
    session_id = await _start_session(client, di, flow_id=flow_id, context_id=context_id)
    service = di.flow_ui_share_service
    tokens = get_token_service()

    created = await service.create(
        request=_share_request(
            flow_id=flow_id, context_id=context_id, redacted_paths=["/secret", "/secret"]
        ),
        company_id=company_id,
        user_id=owner_user_id,
        public_host="linnex.io",
    )
    grant = created.grant
    assert "/l/" in created.share_url
    assert grant.branch_id == "default"
    assert grant.permission == "viewer"
    assert grant.redacted_paths == ["/secret"]

    listed = await service.list_for_owner(
        company_id=company_id,
        user_id=owner_user_id,
        flow_id=flow_id,
        context_id=context_id,
    )
    assert [item.grant_id for item in listed] == [grant.grant_id]

    with pytest.raises(PermissionError, match="read-only"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
            require_editor=True,
        )
    with pytest.raises(PermissionError, match="scope mismatch"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id="other-company",
            flow_id=flow_id,
            context_id=context_id,
        )
    with pytest.raises(PermissionError, match="scope mismatch"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id="another-context",
        )

    exchanged = await service.exchange(grant_id=grant.grant_id, origin="https://linnex.io")
    token_data = tokens.validate_token(exchanged.token)
    assert token_data is not None
    assert token_data.token_type == TokenType.FLOW_UI_SHARE
    assert token_data.metadata["flow_ui_share_context_id"] == context_id
    assert token_data.metadata["flow_ui_share_branch_id"] == "default"
    assert token_data.metadata["flow_ui_share_origin"] == "https://linnex.io"
    assert exchanged.permission == "viewer"
    assert exchanged.flow_id == flow_id
    assert exchanged.context_id == context_id
    assert exchanged.redacted_paths == ["/secret"]

    code = created.share_url.rstrip("/").split("/l/")[-1]
    redirect = await di.short_link_service.resolve_absolute_redirect_url(
        code, host="linnex.io"
    )
    assert redirect is not None
    assert f"grant={grant.grant_id}" in redirect
    assert "/flow-session-share" in redirect

    assert await service.revoke(
        grant_id=grant.grant_id, company_id=company_id, user_id=owner_user_id
    )
    with pytest.raises(PermissionError, match="expired or revoked"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )
    reloaded = await load_flow_ui_state(session_id, di)
    assert reloaded.branch_id == "default"


@pytest.mark.asyncio
async def test_share_requires_owner_and_tracks_durable_scope_drift(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
    di,
) -> None:
    _ = app
    owner_user_id, company_id = _owner_scope(auth_token_system)
    flow_id = f"share-scope-{unique_id}"
    context_id = f"ctx-scope-{unique_id}"
    session_id = await _start_session(client, di, flow_id=flow_id, context_id=context_id)
    service = di.flow_ui_share_service

    with pytest.raises(ValueError, match="does not exist"):
        _ = await service.create(
            request=_share_request(flow_id=flow_id, context_id="never-started"),
            company_id=company_id,
            user_id=owner_user_id,
            public_host="linnex.io",
        )
    with pytest.raises(PermissionError, match="Only the Flow UI session owner"):
        _ = await service.create(
            request=_share_request(flow_id=flow_id, context_id=context_id),
            company_id=company_id,
            user_id="not-the-owner",
            public_host="linnex.io",
        )
    with pytest.raises(ValueError, match="system field"):
        _ = await service.create(
            request=_share_request(
                flow_id=flow_id, context_id=context_id, redacted_paths=["/task_id"]
            ),
            company_id=company_id,
            user_id=owner_user_id,
            public_host="linnex.io",
        )

    created = await service.create(
        request=_share_request(flow_id=flow_id, context_id=context_id, permission="editor"),
        company_id=company_id,
        user_id=owner_user_id,
        public_host="linnex.io",
    )
    _ = await service.authorize(
        grant_id=created.grant.grant_id,
        company_id=company_id,
        flow_id=flow_id,
        context_id=context_id,
        require_editor=True,
    )

    state = await load_flow_ui_state(session_id, di)
    drifted = state.model_copy(update={"branch_id": "other-branch"})
    await di.workflow_runtime.save_state(session_id, drifted)
    with pytest.raises(PermissionError, match="durable identity"):
        _ = await service.authorize(
            grant_id=created.grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )


@pytest.mark.asyncio
async def test_expired_grant_is_inactive_via_repository(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
    di,
) -> None:
    _ = app
    owner_user_id, company_id = _owner_scope(auth_token_system)
    flow_id = f"share-exp-{unique_id}"
    context_id = f"ctx-exp-{unique_id}"
    _ = await _start_session(client, di, flow_id=flow_id, context_id=context_id)
    service = di.flow_ui_share_service
    expired = FlowUIShareGrant(
        grant_id=f"expired-grant-{unique_id}-pad-to-24chars",
        company_id=company_id,
        flow_id=flow_id,
        branch_id="default",
        context_id=context_id,
        permission="viewer",
        created_by_user_id=owner_user_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    _ = await FlowUIShareGrant.set(expired)
    with pytest.raises(PermissionError, match="expired or revoked"):
        _ = await service.authorize(
            grant_id=expired.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )
    assert await FlowUIShareGrant.active_for_grant(expired.grant_id) is None
    with pytest.raises(ValueError, match="grant_id is required"):
        _ = await FlowUIShareGrant.active_for_grant("")
