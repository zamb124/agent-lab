"""HTTP-контракт HITL conversation + WorkItem complete. Без моков."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.state.interrupt import HandoffMode
from core.worktracker.models import WorkItemState
from tests.flows.hitl_test_harness import park_hitl_session
from tests.sync.api._helpers import upload_platform_file

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60, func_only=True)]

HITL_API = "/flows/api/v1/hitl"
WORK_ITEMS = "/worktracker/api/v1/work-items"


async def test_takeover_operator_message_http_appends_without_resume(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    text = f"оператор {unique_id}"
    send = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json={"text": text, "idempotency_key": f"k-{unique_id}"},
    )
    assert send.status_code == 200
    turn = send.json()
    assert turn["role"] == "operator"
    assert turn["text"] == text

    snapshot = await client.get(f"{HITL_API}/{parked.work_item_id}/conversation")
    assert snapshot.status_code == 200
    body = snapshot.json()
    operator_turns = [t for t in body["turns"] if t["role"] == "operator"]
    assert len(operator_turns) == 1
    assert operator_turns[0]["text"] == text

    item = await container.work_item_service.get("system", parked.work_item_id)
    assert item.state is WorkItemState.OPEN
    state = await container.workflow_runtime.get_state(parked.session_id)
    assert state is not None
    assert state.interrupt is not None


async def test_single_reply_operator_ask_http_rejected(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.SINGLE_REPLY, owner_user_id=system_user_id
    )
    send = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json={"text": "ask", "idempotency_key": f"k-{unique_id}"},
    )
    assert send.status_code == 400
    assert send.json()["error_code"] == "ws_invalid_payload"


async def test_operator_message_http_forbidden_for_queue_outsider(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
    auth_headers_system_user2: dict[str, str],
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    send = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        headers=auth_headers_system_user2,
        json={"text": "hi", "idempotency_key": f"k-{unique_id}"},
    )
    assert send.status_code == 403
    assert send.json()["error_code"] == "forbidden"


async def test_takeover_operator_message_http_with_file_ids(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    frontend_client,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    upload = await upload_platform_file(
        frontend_client,
        auth_headers_system,
        filename=f"hitl-{unique_id}.txt",
        content=b"operator file",
        content_type="text/plain",
        is_public=False,
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]
    send = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json={
            "text": f"файл {unique_id}",
            "idempotency_key": f"k-file-{unique_id}",
            "file_ids": [file_id],
        },
    )
    assert send.status_code == 200
    turn = send.json()
    assert turn["role"] == "operator"
    assert turn["file_ids"] == [file_id]


async def test_single_reply_complete_http_requires_resolution(
    app,
    container,
    worktracker_container,
    worktracker_client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.SINGLE_REPLY, owner_user_id=system_user_id
    )
    empty = await worktracker_client.post(
        f"{WORK_ITEMS}/{parked.work_item_id}/complete",
        json={"resolution_text": ""},
    )
    assert empty.status_code == 400
    detail = empty.json()["detail"]
    assert "single_reply" in str(detail)
    open_item = await container.work_item_service.get("system", parked.work_item_id)
    assert open_item.state is WorkItemState.OPEN

    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{parked.work_item_id}/complete",
        json={"resolution_text": f"ответ {unique_id}"},
    )
    assert done.status_code == 200
    assert done.json()["state"] == "done"


async def test_takeover_complete_http_allows_empty_resolution(
    app,
    container,
    worktracker_container,
    worktracker_client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{parked.work_item_id}/complete",
        json={"resolution_text": ""},
    )
    assert done.status_code == 200
    assert done.json()["state"] == "done"


async def test_operator_message_http_idempotent(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    payload = {"text": f"idem {unique_id}", "idempotency_key": f"same-{unique_id}"}
    first = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json=payload,
    )
    second = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["message_id"] == second.json()["message_id"]
    snapshot = await client.get(f"{HITL_API}/{parked.work_item_id}/conversation")
    operator_turns = [t for t in snapshot.json()["turns"] if t["role"] == "operator"]
    assert len(operator_turns) == 1


async def test_terminal_hitl_rejects_send_and_second_complete(
    app,
    container,
    worktracker_container,
    client: AsyncClient,
    worktracker_client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked = await park_hitl_session(
        container, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{parked.work_item_id}/complete",
        json={"resolution_text": ""},
    )
    assert done.status_code == 200

    send = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json={"text": "late", "idempotency_key": f"late-{unique_id}"},
    )
    assert send.status_code == 400
    assert send.json()["error_code"] == "ws_invalid_payload"

    again = await worktracker_client.post(
        f"{WORK_ITEMS}/{parked.work_item_id}/complete",
        json={"resolution_text": "again"},
    )
    assert again.status_code == 200
    assert again.json()["state"] == "done"
