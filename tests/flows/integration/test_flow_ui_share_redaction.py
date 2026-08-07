"""Share redaction on the live A2A wire (real DB, Redis, HTTP — no mocks)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from apps.flows.src.container import get_container
from core.a2a import PLATFORM_UI_BOOTSTRAP_ACTION, PLATFORM_UI_SYNC_ACTION
from core.context import require_context
from core.models.flow_ui_share import FlowUIShareCreateRequest
from tests.flows._flow_ui_session import (
    a2a_flow_ui_send,
    bootstrap_flow_ui_session,
    sync_flow_ui_session,
)
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow

_SHARE_HOST_HEADERS = {"Host": "linnex.io"}
_SHARE_EXCHANGE_HEADERS = {"Host": "linnex.io", "Origin": "http://linnex.io"}


def _artifact_blob(task: dict[str, Any]) -> str:
    return json.dumps(task.get("artifacts") or [], ensure_ascii=False)


@pytest.mark.asyncio
async def test_a2a_share_bootstrap_redacts_forbidden_value_paths(
    client: AsyncClient,
    app: object,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = app
    _ = auth_token_system
    _ = require_context()
    flow_id = f"a2a_share_redact_{unique_id}"
    context_id = f"ctx-redact-{unique_id}"
    session_id = f"{flow_id}:{context_id}"
    secret = f"TOP-SECRET-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        bootstrap = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-{unique_id}",
        )
        assert bootstrap["status"]["state"] == "TASK_STATE_COMPLETED"

        synced = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id=f"sync-{unique_id}",
            revision=1,
            message_value=secret,
        )
        assert synced["status"]["state"] == "TASK_STATE_COMPLETED"
        owner_blob = _artifact_blob(synced)
        assert secret in owner_blob

        state = await get_container().workflow_runtime.get_state(session_id)
        assert state is not None
        assert state.ui_document.surfaces["main"].data_model.values["message"] == secret

        created = await client.post(
            "/flows/api/v1/flow-ui/shares",
            headers=_SHARE_HOST_HEADERS,
            json={
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": state.ui_document.revision,
                "permission": "view",
                "redacted_value_paths": ["/values/message"],
                "expires_in_seconds": 300,
            },
        )
        assert created.status_code == 200, created.text
        grant_body = created.json()["grant"]
        assert grant_body["redacted_value_paths"] == ["/values/message"]
        grant_id = grant_body["grant_id"]

        exchanged = await client.post(
            f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
            headers=_SHARE_EXCHANGE_HEADERS,
        )
        assert exchanged.status_code == 200, exchanged.text
        exchange_body = exchanged.json()
        assert exchange_body["flows_base_url"] == "/flows"
        assert exchange_body["redacted_value_paths"] == ["/values/message"]
        share_token = exchange_body["token"]

        viewer_bootstrap = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"viewer-bootstrap-{uuid.uuid4().hex}",
            auth_headers={
                "Host": "linnex.io",
                "Origin": "http://linnex.io",
                "Authorization": f"Bearer {share_token}",
            },
        )
        viewer_blob = _artifact_blob(viewer_bootstrap)
        assert secret not in viewer_blob
        assert "flow-ui:" in viewer_blob or "ui.surface" in viewer_blob

        owner_reload = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"owner-reload-{uuid.uuid4().hex}",
        )
        assert secret in _artifact_blob(owner_reload)

        durable = await get_container().workflow_runtime.get_state(session_id)
        assert durable is not None
        assert durable.ui_document.surfaces["main"].data_model.values["message"] == secret
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_share_interact_cannot_write_redacted_paths(
    app: object,
    unique_id: str,
) -> None:
    _ = app
    context = require_context()
    company_id = context.active_company.company_id if context.active_company else None
    if company_id is None:
        raise AssertionError("active company required")

    flow_id, context_id, _, bootstrapped = await bootstrap_flow_ui_session(
        flow_id=f"share-write-redact-{unique_id}",
        context_id=f"ctx-write-redact-{unique_id}",
    )
    synced = await sync_flow_ui_session(
        flow_id=flow_id,
        context_id=context_id,
        revision=bootstrapped.state.ui_document.revision,
        message_value="owner-secret",
    )
    created = await get_container().flow_ui_share_service.create(
        request=FlowUIShareCreateRequest.model_validate(
            {
                "flow_id": flow_id,
                "context_id": context_id,
                "document_id": f"flow-ui:{context_id}",
                "minimum_revision": synced.state.ui_document.revision,
                "permission": "interact",
                "redacted_value_paths": ["/values/message"],
                "expires_in_seconds": 300,
            }
        ),
        company_id=company_id,
        user_id=context.user.user_id,
        public_host="linnex.io",
    )
    grant = created.grant
    with pytest.raises(PermissionError, match="forbids client writes"):
        await sync_flow_ui_session(
            flow_id=flow_id,
            context_id=context_id,
            revision=synced.state.ui_document.revision,
            message_value="attempted-leak",
            share_grant=grant,
        )
