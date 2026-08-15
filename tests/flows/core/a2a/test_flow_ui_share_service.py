"""FlowUIShareService against real repository, workflow runtime and short links."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.flows.src.container import get_container
from core.context import require_context
from core.models.flow_ui_share import FlowUIShareCreateRequest, FlowUIShareGrant
from core.utils.tokens import TokenType, get_token_service
from tests.flows._flow_ui_session import (
    bootstrap_flow_ui_session,
    load_flow_ui_state,
    sync_flow_ui_session,
)


def _share_request(
    *,
    flow_id: str,
    context_id: str,
    revision: int,
    permission: str = "viewer",
) -> FlowUIShareCreateRequest:
    return FlowUIShareCreateRequest.model_validate(
        {
            "flow_id": flow_id,
            "context_id": context_id,
            "document_id": f"flow-ui:{context_id}",
            "minimum_revision": revision,
            "permission": permission,
            "expires_in_seconds": 300,
        }
    )


@pytest.mark.asyncio
async def test_live_share_is_exact_scoped_revocable_and_read_only_by_default(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    context = require_context()
    company_id = context.active_company.company_id if context.active_company else None
    if company_id is None:
        raise AssertionError("active company required")
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-svc-{unique_id}",
        context_id=f"ctx-{unique_id}",
    )
    service = get_container().flow_ui_share_service
    tokens = get_token_service()

    created = await service.create(
        request=_share_request(
            flow_id=flow_id,
            context_id=context_id,
            revision=bootstrapped.state.ui_document.revision,
        ),
        company_id=company_id,
        user_id=context.user.user_id,
        public_host="linnex.io",
    )
    grant = created.grant
    assert "/l/" in created.share_url
    assert grant.branch_id == "default"
    assert grant.minimum_revision == bootstrapped.state.ui_document.revision == 1
    assert grant.permission == "viewer"
    assert grant.document_id == f"flow-ui:{context_id}"

    listed = await service.list_for_owner(
        company_id=company_id,
        user_id=context.user.user_id,
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
    with pytest.raises(PermissionError, match="document scope mismatch"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
            document_id="another-document",
        )

    exchanged = await service.exchange(
        grant_id=grant.grant_id,
        origin="https://linnex.io",
    )
    token_data = tokens.validate_token(exchanged.token)
    assert token_data is not None
    assert token_data.token_type == TokenType.FLOW_UI_SHARE
    assert token_data.metadata["flow_ui_share_context_id"] == context_id
    assert token_data.metadata["flow_ui_share_branch_id"] == "default"
    assert token_data.metadata["flow_ui_share_origin"] == "https://linnex.io"
    assert exchanged.permission == "viewer"
    assert exchanged.flow_id == flow_id
    assert exchanged.context_id == context_id
    assert exchanged.document_id == f"flow-ui:{context_id}"

    code = created.share_url.rstrip("/").split("/l/")[-1]
    redirect = await get_container().short_link_service.resolve_absolute_redirect_url(
        code,
        host="linnex.io",
    )
    assert redirect is not None
    assert f"grant={grant.grant_id}" in redirect
    assert "/flow-session-share" in redirect

    assert await service.revoke(
        grant_id=grant.grant_id,
        company_id=company_id,
        user_id=context.user.user_id,
    )
    with pytest.raises(PermissionError, match="expired or revoked"):
        _ = await service.authorize(
            grant_id=grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document.revision == 1


@pytest.mark.asyncio
async def test_share_rejects_unacknowledged_revision_and_durable_scope_drift(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    context = require_context()
    company_id = context.active_company.company_id if context.active_company else None
    if company_id is None:
        raise AssertionError("active company required")
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-occ-{unique_id}",
        context_id=f"ctx-occ-{unique_id}",
    )
    service = get_container().flow_ui_share_service

    with pytest.raises(ValueError, match="latest server-acknowledged"):
        _ = await service.create(
            request=_share_request(
                flow_id=flow_id,
                context_id=context_id,
                revision=bootstrapped.state.ui_document.revision + 1,
            ),
            company_id=company_id,
            user_id=context.user.user_id,
            public_host="linnex.io",
        )
    with pytest.raises(PermissionError, match="Only the Flow UI session owner"):
        _ = await service.create(
            request=_share_request(
                flow_id=flow_id,
                context_id=context_id,
                revision=bootstrapped.state.ui_document.revision,
            ),
            company_id=company_id,
            user_id="not-the-owner",
            public_host="linnex.io",
        )

    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="pending-before-share",
    )
    assert synced.state.ui_document.revision == 2

    with pytest.raises(ValueError, match="latest server-acknowledged"):
        _ = await service.create(
            request=_share_request(
                flow_id=flow_id,
                context_id=context_id,
                revision=1,
            ),
            company_id=company_id,
            user_id=context.user.user_id,
            public_host="linnex.io",
        )

    created = await service.create(
        request=_share_request(
            flow_id=flow_id,
            context_id=context_id,
            revision=2,
            permission="editor",
        ),
        company_id=company_id,
        user_id=context.user.user_id,
        public_host="linnex.io",
    )
    _ = await service.authorize(
        grant_id=created.grant.grant_id,
        company_id=company_id,
        flow_id=flow_id,
        context_id=context_id,
        require_editor=True,
    )

    state = await load_flow_ui_state(session_id)
    drifted = state.model_copy(update={"branch_id": "other-branch"})
    await get_container().workflow_runtime.save_state(session_id, drifted)
    with pytest.raises(PermissionError, match="durable identity"):
        _ = await service.authorize(
            grant_id=created.grant.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )


@pytest.mark.asyncio
async def test_expired_grant_is_inactive_via_repository(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    context = require_context()
    company_id = context.active_company.company_id if context.active_company else None
    if company_id is None:
        raise AssertionError("active company required")
    flow_id, context_id, _, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-exp-{unique_id}",
        context_id=f"ctx-exp-{unique_id}",
    )
    repository = get_container().flow_ui_share_repository
    service = get_container().flow_ui_share_service
    expired = FlowUIShareGrant(
        grant_id=f"expired-grant-{unique_id}-pad-to-24chars",
        company_id=company_id,
        flow_id=flow_id,
        branch_id="default",
        context_id=context_id,
        document_id=f"flow-ui:{context_id}",
        minimum_revision=bootstrapped.state.ui_document.revision,
        permission="viewer",
        created_by_user_id=context.user.user_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    _ = await repository.create(expired)
    with pytest.raises(PermissionError, match="expired or revoked"):
        _ = await service.authorize(
            grant_id=expired.grant_id,
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )
    assert await repository.get_active(expired.grant_id) is None
