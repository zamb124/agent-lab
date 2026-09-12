"""Ход пользователя (текст или ui-action) во время HITL takeover: append в диалог, граф не возобновляется."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from core.worktracker.models import WorkItemState
from tests.flows._a2a_v1 import A2A_HEADERS, SEND_MESSAGE, a2a_rpc, a2a_text_message
from tests.flows._flow_ui_session import a2a_send, ui_action_message
from tests.flows.a2a_conformance.helpers.flows import delete_flow
from tests.flows.hitl_test_harness import (
    hitl_flow_create_payload,
    park_hitl_session,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60, func_only=True)]

HITL_API = "/flows/api/v1/hitl"


def _task_interrupt_kind(task: object) -> str | None:
    if not isinstance(task, dict):
        raise AssertionError(f"A2A task must be object, got {type(task)}")
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    message = status.get("message")
    metadata = {}
    if isinstance(message, dict) and isinstance(message.get("metadata"), dict):
        metadata = message["metadata"]
    elif isinstance(task.get("metadata"), dict):
        metadata = task["metadata"]
    interrupt = metadata.get("platform_interrupt")
    if not isinstance(interrupt, dict):
        return None
    body = interrupt.get("body")
    if not isinstance(body, dict):
        return None
    kind = body.get("kind")
    return kind if isinstance(kind, str) else None


def _task_status_text(task: object) -> str:
    if not isinstance(task, dict):
        raise AssertionError(f"A2A task must be object, got {type(task)}")
    status = task.get("status")
    if not isinstance(status, dict):
        return ""
    message = status.get("message")
    if not isinstance(message, dict):
        return ""
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "".join(chunks)


async def _create_hitl_flow(
    client: AsyncClient, *, flow_id: str, queue_slug: str, mode: HandoffMode
) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json=hitl_flow_create_payload(flow_id=flow_id, queue_slug=queue_slug, mode=mode),
    )
    assert response.status_code == 200, response.text


async def test_a2a_user_message_appends_during_hitl_takeover(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    flow_id = f"hitl_takeover_{unique_id}"
    parked = await park_hitl_session(
        container,
        unique_id,
        mode=HandoffMode.TAKEOVER,
        owner_user_id=system_user_id,
        flow_id=flow_id,
    )
    await _create_hitl_flow(
        client,
        flow_id=flow_id,
        queue_slug=parked.queue_slug,
        mode=HandoffMode.TAKEOVER,
    )
    text = f"покупатель {unique_id}"
    send = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers=A2A_HEADERS,
        json=a2a_rpc(
            SEND_MESSAGE,
            {
                "message": a2a_text_message(
                    text,
                    task_id=parked.task_id,
                    context_id=parked.context_id,
                )
            },
        ),
    )
    assert send.status_code == 200, send.text
    body = send.json()
    assert "error" not in body, body
    task = body["result"]
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert _task_interrupt_kind(task) == "operator_task"
    assert text not in _task_status_text(task)

    snapshot = await client.get(f"{HITL_API}/{parked.work_item_id}/conversation")
    assert snapshot.status_code == 200, snapshot.text
    user_turns = [t for t in snapshot.json()["turns"] if t["role"] == "user"]
    assert any(t["text"] == text for t in user_turns)

    item = await container.work_item_service.get("system", parked.work_item_id)
    assert item.state is WorkItemState.OPEN
    state = await container.workflow_runtime.get_state(parked.session_id)
    assert state is not None
    assert state.interrupt is not None
    assert isinstance(state.interrupt.body, OperatorTaskInterrupt)
    assert state.interrupt.body.handoff_mode == HandoffMode.TAKEOVER


async def test_ui_action_appends_during_hitl_takeover(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    flow_id = f"hitl_ui_takeover_{unique_id}"
    parked = await park_hitl_session(
        container,
        unique_id,
        mode=HandoffMode.TAKEOVER,
        owner_user_id=system_user_id,
        flow_id=flow_id,
    )
    await _create_hitl_flow(
        client,
        flow_id=flow_id,
        queue_slug=parked.queue_slug,
        mode=HandoffMode.TAKEOVER,
    )
    try:
        text = f"submit {unique_id}"
        submitted = await a2a_send(
            client,
            flow_id=flow_id,
            message=ui_action_message(
                context_id=parked.context_id,
                task_id=parked.task_id,
                action="send",
                source="conversation",
                payload={"text": text},
            ),
        )
        assert submitted["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert _task_interrupt_kind(submitted) == "operator_task"
        assert text not in _task_status_text(submitted)
        snapshot = await client.get(f"{HITL_API}/{parked.work_item_id}/conversation")
        assert snapshot.status_code == 200, snapshot.text
        user_turns = [t for t in snapshot.json()["turns"] if t["role"] == "user"]
        assert any("send" in t["text"] for t in user_turns)
        item = await container.work_item_service.get("system", parked.work_item_id)
        assert item.state is WorkItemState.OPEN
        state = await container.workflow_runtime.get_state(parked.session_id)
        assert state is not None
        assert state.interrupt is not None
    finally:
        await delete_flow(client, flow_id)
