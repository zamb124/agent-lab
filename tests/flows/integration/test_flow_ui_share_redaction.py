"""Share-редакция артефакта ``state`` на живом A2A (реальные БД, Redis, HTTP)."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from core.flow_ui.document import (
    FlowUIButton,
    FlowUIConversation,
    FlowUIDocument,
    FlowUIPage,
    FlowUITextInput,
)
from core.types import JsonObject
from tests.flows._flow_ui_session import (
    a2a_get_task,
    a2a_send,
    a2a_send_error,
    ensure_flow,
    state_from_task,
    text_message,
    ui_action_message,
)

_SHARE_HOST_HEADERS = {"Host": "linnex.io"}
_SHARE_EXCHANGE_HEADERS = {"Host": "linnex.io", "Origin": "http://linnex.io"}


def _artifact_blob(task: JsonObject) -> str:
    return json.dumps(task.get("artifacts"), ensure_ascii=False)


def _secret_interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                FlowUIPage(
                    page_id="main",
                    title="Main",
                    blocks=[
                        FlowUITextInput(block_id="secret_input", field="secret", label="Secret"),
                        FlowUITextInput(block_id="note_input", field="note", label="Note"),
                        FlowUIButton(block_id="save", label="Save", action={"name": "save"}),
                        FlowUIConversation(block_id="conversation"),
                    ],
                )
            ],
        }
    )


async def _share_token(
    client: AsyncClient,
    *,
    flow_id: str,
    context_id: str,
    permission: str,
    redacted_paths: list[str],
) -> str:
    created = await client.post(
        "/flows/api/v1/flow-ui/shares",
        headers=_SHARE_HOST_HEADERS,
        json={
            "flow_id": flow_id,
            "context_id": context_id,
            "permission": permission,
            "redacted_paths": redacted_paths,
            "expires_in_seconds": 300,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["grant"]["redacted_paths"] == redacted_paths
    grant_id = created.json()["grant"]["grant_id"]
    exchanged = await client.post(
        f"/flows/api/v1/flow-ui/shares/exchange/{grant_id}",
        headers=_SHARE_EXCHANGE_HEADERS,
    )
    assert exchanged.status_code == 200, exchanged.text
    assert exchanged.json()["flows_base_url"] == "/flows"
    assert exchanged.json()["redacted_paths"] == redacted_paths
    return exchanged.json()["token"]


def _share_headers(token: str) -> dict[str, str]:
    return {"Host": "linnex.io", "Origin": "http://linnex.io", "Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_share_viewer_reads_task_without_redacted_state_paths(
    client: AsyncClient,
    app: object,
    unique_id: str, di,
) -> None:
    _ = app
    flow_id = f"a2a_share_redact_{unique_id}"
    context_id = f"ctx-redact-{unique_id}"
    secret = f"TOP-SECRET-{unique_id}"
    _ = await ensure_flow(flow_id=flow_id, interface=_secret_interface(), di=di)

    owner_task = await a2a_send(
        client,
        flow_id=flow_id,
        message=ui_action_message(
            context_id=context_id,
            action="save",
            source="save",
            fields={"secret": secret, "note": "visible"},
        ),
    )
    assert owner_task["status"]["state"] == "TASK_STATE_COMPLETED", owner_task
    task_id = owner_task["id"]
    assert state_from_task(owner_task) == {"secret": secret, "note": "visible"}

    token = await _share_token(
        client,
        flow_id=flow_id,
        context_id=context_id,
        permission="viewer",
        redacted_paths=["/secret"],
    )
    viewer_task = await a2a_get_task(
        client, flow_id=flow_id, task_id=task_id, auth_headers=_share_headers(token)
    )
    assert secret not in _artifact_blob(viewer_task)
    assert state_from_task(viewer_task) == {"note": "visible"}

    owner_reload = await a2a_get_task(client, flow_id=flow_id, task_id=task_id)
    assert state_from_task(owner_reload) == {"secret": secret, "note": "visible"}

    viewer_send = await a2a_send_error(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hello from viewer"),
        auth_headers=_share_headers(token),
    )
    assert "read-only" in json.dumps(viewer_send)


@pytest.mark.asyncio
async def test_share_editor_cannot_write_redacted_paths(
    client: AsyncClient,
    app: object,
    unique_id: str, di,
) -> None:
    _ = app
    flow_id = f"a2a_share_write_{unique_id}"
    context_id = f"ctx-write-{unique_id}"
    _ = await ensure_flow(flow_id=flow_id, interface=_secret_interface(), di=di)

    owner_task = await a2a_send(
        client,
        flow_id=flow_id,
        message=ui_action_message(
            context_id=context_id,
            action="save",
            source="save",
            fields={"secret": "owner-secret", "note": "first"},
        ),
    )
    assert owner_task["status"]["state"] == "TASK_STATE_COMPLETED", owner_task

    token = await _share_token(
        client,
        flow_id=flow_id,
        context_id=context_id,
        permission="editor",
        redacted_paths=["/secret"],
    )
    leak = await a2a_send_error(
        client,
        flow_id=flow_id,
        message=ui_action_message(
            context_id=context_id,
            action="save",
            source="save",
            fields={"secret": "attempted-leak", "note": "second"},
        ),
        auth_headers=_share_headers(token),
    )
    assert "redacted path" in json.dumps(leak)

    allowed = await a2a_send(
        client,
        flow_id=flow_id,
        message=ui_action_message(
            context_id=context_id,
            action="save",
            source="save",
            fields={"note": "second"},
        ),
        auth_headers=_share_headers(token),
    )
    assert allowed["status"]["state"] == "TASK_STATE_COMPLETED", allowed
    assert state_from_task(allowed) == {"note": "second"}

    owner_view = await a2a_get_task(client, flow_id=flow_id, task_id=allowed["id"])
    assert state_from_task(owner_view) == {"secret": "owner-secret", "note": "second"}
