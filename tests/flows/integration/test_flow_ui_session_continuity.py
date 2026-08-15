"""Session continuity: autosync, OCC, reopen, share revision gate (real durable ledger)."""

from __future__ import annotations

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.services.flow_ui_session_service import FlowUIDuplicateMutationError
from apps.flows.src.services.flow_ui_share_service import flow_ui_share_visitor_user_id
from core.context import require_context
from core.models.flow_interface import default_flow_interface_config
from core.models.flow_ui_share import FlowUIShareCreateRequest, FlowUIShareCreateResponse
from core.state.flow_ui import FlowUIDocument
from core.state.flow_ui_delta import FlowUIRevisionConflictError
from tests.flows._flow_ui_session import (
    bootstrap_flow_ui_session,
    load_flow_ui_state,
    submit_flow_ui_session,
    sync_flow_ui_session,
)


def _company_id() -> str:
    context = require_context()
    company_id = context.active_company.company_id if context.active_company else None
    if company_id is None:
        raise AssertionError("active company required")
    return company_id


async def _create_share(
    *,
    flow_id: str,
    context_id: str,
    revision: int,
    permission: str,
) -> FlowUIShareCreateResponse:
    context = require_context()
    return await get_container().flow_ui_share_service.create(
        request=FlowUIShareCreateRequest.model_validate(
            {
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": revision,
                "permission": permission,
                "expires_in_seconds": 300,
            }
        ),
        company_id=_company_id(),
        user_id=context.user.user_id,
        public_host="linnex.io",
    )


@pytest.mark.asyncio
async def test_autosync_preserves_values_and_view_state_across_reload(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"cont-reload-{unique_id}",
        context_id=f"ctx-reload-{unique_id}",
    )
    assert bootstrapped.state.ui_document.revision == 1

    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value=f"draft-{unique_id}",
        values={"message": f"draft-{unique_id}", "files": []},
        session_view_state={
            "activeTabs": {"main": "conversation"},
            "openSurfaces": ["details"],
        },
    )
    assert synced.was_applied
    assert synced.state.ui_document.revision == 2
    assert synced.state.ui_document.surfaces["main"].data_model.values == {
        "message": f"draft-{unique_id}",
        "files": [],
    }
    assert "forged" not in synced.state.ui_document.surfaces["main"].data_model.content
    assert synced.state.ui_document.session_view_state == {
        "activeTabs": {"main": "conversation"},
        "openSurfaces": ["details"],
    }

    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document == synced.state.ui_document
    assert reloaded.ui_document.document_id == f"flow-ui:{context_id}"
    assert reloaded.session_flow_id == flow_id


@pytest.mark.asyncio
async def test_autosync_does_not_open_submit_interaction(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, _ = await bootstrap_flow_ui_session(
        flow_id=f"cont-nosubmit-{unique_id}",
        context_id=f"ctx-nosubmit-{unique_id}",
    )
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="only-sync",
    )
    assert synced.was_applied
    assert synced.content == "only-sync"
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_interaction is None
    assert reloaded.content is None


@pytest.mark.asyncio
async def test_forced_sync_then_submit_is_atomic_revision_chain(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, _ = await bootstrap_flow_ui_session(
        flow_id=f"cont-submit-{unique_id}",
        context_id=f"ctx-submit-{unique_id}",
    )
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="before-submit",
    )
    assert synced.state.ui_document.revision == 2
    submitted = await submit_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=2,
        message_value="run-now",
    )
    assert submitted.was_applied
    assert submitted.content == "run-now"
    assert submitted.state.ui_document.revision == 3
    assert submitted.state.ui_interaction is not None
    assert submitted.state.ui_interaction.accepted_revision == 3
    assert submitted.state.ui_interaction.validated_values_snapshot == {
        "main": {"message": "run-now", "files": []}
    }
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document.revision == 3
    assert reloaded.ui_interaction == submitted.state.ui_interaction


@pytest.mark.asyncio
async def test_stale_and_duplicate_mutations_fail_closed(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, _, _ = await bootstrap_flow_ui_session(
        flow_id=f"cont-occ-{unique_id}",
        context_id=f"ctx-occ-{unique_id}",
    )
    first = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="v1",
        action_id="mutation-same",
    )
    assert first.was_applied
    duplicate = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="v1",
        action_id="mutation-same",
    )
    assert not duplicate.was_applied
    assert duplicate.state.ui_document.revision == 2

    with pytest.raises(FlowUIDuplicateMutationError):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="different-payload",
            action_id="mutation-same",
        )
    with pytest.raises(FlowUIRevisionConflictError):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="stale",
            action_id="mutation-stale",
        )


@pytest.mark.asyncio
async def test_share_waits_for_acknowledged_revision_after_autosync(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    context = require_context()
    flow_id, context_id, _, _ = await bootstrap_flow_ui_session(
        flow_id=f"cont-share-{unique_id}",
        context_id=f"ctx-share-{unique_id}",
    )
    service = get_container().flow_ui_share_service
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="share-me",
    )
    with pytest.raises(ValueError, match="latest server-acknowledged"):
        _ = await service.create(
            request=FlowUIShareCreateRequest.model_validate(
                {
                    "flow_id": flow_id,
                    "context_id": context_id,
                    "document_id": f"flow-ui:{context_id}",
                    "minimum_revision": 1,
                    "permission": "viewer",
                    "expires_in_seconds": 300,
                }
            ),
            company_id=_company_id(),
            user_id=context.user.user_id,
            public_host="linnex.io",
        )
    created = await service.create(
        request=FlowUIShareCreateRequest.model_validate(
            {
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": synced.state.ui_document.revision,
                "permission": "viewer",
                "expires_in_seconds": 300,
            }
        ),
        company_id=_company_id(),
        user_id=context.user.user_id,
        public_host="linnex.io",
    )
    assert created.grant.minimum_revision == 2
    assert created.grant.context_id == context_id


@pytest.mark.asyncio
async def test_second_bootstrap_same_context_returns_authoritative_snapshot(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, first = await bootstrap_flow_ui_session(
        flow_id=f"cont-tab-{unique_id}",
        context_id=f"ctx-tab-{unique_id}",
    )
    _ = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="from-first-tab",
    )
    _, _, _, second = await bootstrap_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
    )
    assert second.state.ui_document.revision == 2
    assert second.state.ui_document.surfaces["main"].data_model.values["message"] == (
        "from-first-tab"
    )
    assert second.state.ui_document.document_id == first.state.ui_document.document_id
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document == second.state.ui_document


@pytest.mark.asyncio
async def test_view_share_cannot_sync_or_submit_interact_can_sync(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"cont-perm-{unique_id}",
        context_id=f"ctx-perm-{unique_id}",
    )
    view_created = await _create_share(
        flow_id=flow_id,
        context_id=context_id,
        revision=bootstrapped.state.ui_document.revision,
        permission="viewer",
    )
    viewer_user_id = flow_ui_share_visitor_user_id(view_created.grant.grant_id)
    with pytest.raises(PermissionError, match="read-only"):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="viewer-blocked",
            user_id=viewer_user_id,
            share_grant=view_created.grant,
        )
    with pytest.raises(PermissionError, match="read-only"):
        _ = await submit_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="viewer-submit-blocked",
            user_id=viewer_user_id,
            share_grant=view_created.grant,
        )
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document.revision == 1
    assert reloaded.ui_interaction is None

    interact_created = await _create_share(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        permission="editor",
    )
    collaborator_user_id = flow_ui_share_visitor_user_id(interact_created.grant.grant_id)
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value=f"collab-{unique_id}",
        user_id=collaborator_user_id,
        share_grant=interact_created.grant,
    )
    assert synced.was_applied
    assert synced.state.ui_document.revision == 2
    assert synced.state.ui_document.surfaces["main"].data_model.values["message"] == (
        f"collab-{unique_id}"
    )
    assert synced.state.ui_interaction is None


@pytest.mark.asyncio
async def test_owner_and_collaborator_conflict_is_deterministic_occ(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, _, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"cont-race-{unique_id}",
        context_id=f"ctx-race-{unique_id}",
    )
    created = await _create_share(
        flow_id=flow_id,
        context_id=context_id,
        revision=bootstrapped.state.ui_document.revision,
        permission="editor",
    )
    collaborator_user_id = flow_ui_share_visitor_user_id(created.grant.grant_id)
    owner = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        message_value="owner-wins-base",
        action_id=f"owner-{unique_id}",
    )
    assert owner.state.ui_document.revision == 2
    with pytest.raises(FlowUIRevisionConflictError):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="collab-stale",
            action_id=f"collab-{unique_id}",
            user_id=collaborator_user_id,
            share_grant=created.grant,
        )
    rebased = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=2,
        message_value="collab-rebased",
        action_id=f"collab-rebased-{unique_id}",
        user_id=collaborator_user_id,
        share_grant=created.grant,
    )
    assert rebased.was_applied
    assert rebased.state.ui_document.revision == 3
    assert rebased.state.ui_document.surfaces["main"].data_model.values["message"] == (
        "collab-rebased"
    )


@pytest.mark.asyncio
async def test_unbound_values_and_unknown_view_state_fail_closed(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    flow_id, context_id, session_id, _ = await bootstrap_flow_ui_session(
        flow_id=f"cont-sec-{unique_id}",
        context_id=f"ctx-sec-{unique_id}",
    )
    with pytest.raises(ValueError, match="not bound"):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="ignored",
            values={
                "message": "ok",
                "files": [],
                "secret": "injected",
            },
        )
    with pytest.raises(ValueError, match="unknown fields"):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=1,
            message_value="view-state",
            session_view_state={"forgedPanel": True},
        )
    with pytest.raises(FlowUIRevisionConflictError):
        _ = await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=99,
            message_value="future",
        )
    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document.revision == 1
    assert "secret" not in reloaded.ui_document.surfaces["main"].data_model.values


def _chat_document_with_empty_page(*, context_id: str, page_id: str = "page-2") -> FlowUIDocument:
    document = default_flow_interface_config().template.materialize(
        document_id=f"flow-ui:{context_id}"
    )
    payload = document.model_dump(mode="python")
    payload["pages"][page_id] = {
        "page_id": page_id,
        "title": {"default": "Page 2", "translations": {}},
        "route": f"/{page_id}",
        "root_surface_id": page_id,
        "navigation": {"visible": True, "allow_back": True, "allow_direct": True},
        "default_target_profile_id": "runtime",
    }
    payload["surfaces"][page_id] = {
        "surface_id": page_id,
        "catalog_id": document.catalog_id,
        "root_component_id": "root",
        "components": {
            "root": {
                "component_id": "root",
                "type": "PageShell",
                "kind": "container",
                "children": ["submit"],
                "container_layout": {
                    "mode": "grid",
                    "grid": {
                        "columns_by_band": {"compact": 4, "medium": 8, "wide": 12},
                        "column_gap_token": "space.4",
                        "row_gap_token": "space.4",
                        "outer_padding_inline_token": "space.4",
                        "outer_padding_block_token": "space.4",
                        "max_content_width_token": None,
                        "auto_rows": "content",
                        "auto_flow": "row",
                        "align_items": "stretch",
                        "justify_items": "stretch",
                        "baseline_step_token": "space.1",
                    },
                    "stack": None,
                    "flex": None,
                },
            },
            "submit": {
                "component_id": "submit",
                "type": "Button",
                "kind": "leaf",
                "properties": {"label": "Submit", "variant": "primary"},
                "actions": {
                    "press": {
                        "kind": "event",
                        "name": "platform.ui.submit",
                        "context": {},
                    }
                },
            },
        },
        "data_model": {"content": {}, "values": {}, "system": {}},
        "owner": "platform",
        "send_data_model": True,
    }
    return FlowUIDocument.model_validate(payload)


@pytest.mark.asyncio
async def test_navigate_sync_accepts_empty_unbound_page_surface(
    app: object,
    unique_id: str,
) -> None:
    """Client sync of multi-page docs sends {} for pages without value bindings."""
    _ = app
    context_id = f"ctx-nav-{unique_id}"
    document = _chat_document_with_empty_page(context_id=context_id)
    flow_id, context_id, session_id, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"cont-nav-{unique_id}",
        context_id=context_id,
        initial_document=document,
    )
    assert bootstrapped.state.ui_document.revision == 1
    assert "page-2" in bootstrapped.state.ui_document.pages

    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=1,
        surfaces_values={
            "main": {"message": "", "files": []},
            "page-2": {},
        },
        active_page_id="page-2",
    )
    assert synced.was_applied
    assert synced.state.ui_document.revision == 2
    assert synced.state.ui_document.active_page_id == "page-2"

    reloaded = await load_flow_ui_state(session_id)
    assert reloaded.ui_document.active_page_id == "page-2"
    assert reloaded.ui_document.revision == 2
    assert reloaded.ui_interaction is None
