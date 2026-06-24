"""HTTP REST /worktracker/api/v1/work-items — без моков."""

from __future__ import annotations

import io

import pytest

from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.assertions import assert_offset_page, assert_work_item_json
from tests.worktracker.helpers.builders import (
    build_manual_work_item_payload,
    build_queue_assignment,
    build_users_assignment,
)

pytestmark = pytest.mark.asyncio

WORK_ITEMS = f"{API_PREFIX}/work-items"


async def test_list_work_items_offset_page_contract(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    assert create_resp.status_code == 201

    response = await worktracker_client.get(WORK_ITEMS, params={"limit": 10, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert_offset_page(payload)
    assert payload["total"] >= 1
    for item in payload["items"]:
        assert_work_item_json(item)


async def test_list_work_items_filters(
    worktracker_client,
    worktracker_board,
    unique_id: str,
) -> None:
    board_id = worktracker_board.board_id
    created = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id, title=f"Filtered {unique_id}"),
            "board_id": board_id,
            "board_column_id": "todo",
            "kind": "generic",
        },
    )
    assert created.status_code == 201
    work_item_id = created.json()["work_item_id"]

    by_board = await worktracker_client.get(
        WORK_ITEMS,
        params={"board_id": board_id, "kind": "generic", "state": "open"},
    )
    assert by_board.status_code == 200
    ids = {item["work_item_id"] for item in by_board.json()["items"]}
    assert work_item_id in ids

    terminal = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/complete",
        json={"resolution_text": "done"},
    )
    assert terminal.status_code == 200

    open_only = await worktracker_client.get(
        WORK_ITEMS,
        params={"board_id": board_id, "exclude_terminal": True},
    )
    open_ids = {item["work_item_id"] for item in open_only.json()["items"]}
    assert work_item_id not in open_ids


async def test_mine_summary_returns_counts(
    worktracker_client,
    system_user_id: str,
    unique_id: str,
) -> None:
    await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id, title=f"Mine {unique_id}"),
    )
    response = await worktracker_client.get(f"{WORK_ITEMS}/mine/summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["assigned_open_count"] >= 1
    assert summary["queue_inbox_count"] >= 0


async def test_get_work_item_happy_and_404(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    assert create_resp.status_code == 201
    work_item_id = create_resp.json()["work_item_id"]

    get_resp = await worktracker_client.get(f"{WORK_ITEMS}/{work_item_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert_work_item_json(body)
    assert body["state"] == "open"
    assert body["kind"] == "generic"

    missing = await worktracker_client.get(f"{WORK_ITEMS}/wi_missing_{unique_id}")
    assert missing.status_code == 404


async def test_create_manual_task_assigns_creator(
    worktracker_client,
    system_user_id: str,
    unique_id: str,
) -> None:
    response = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["assignment"]["assignee_kind"] == "users"
    assert system_user_id in body["assignment"]["user_ids"]
    assert body["board_id"] is not None


async def test_create_with_variables_and_attachments_roundtrip(
    worktracker_client,
    unique_id: str,
) -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    upload = await worktracker_client.post(
        f"{API_PREFIX}/files/",
        files={"file": ("note.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload.status_code == 200
    file_ref = upload.json()
    file_payload = {
        "file_id": file_ref["file_id"],
        "original_name": file_ref["original_name"],
        "content_type": file_ref["content_type"],
        "file_size": file_ref["file_size"],
        "url": file_ref["url"],
    }

    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id),
            "variables": {
                "priority_hint": {"value": "high", "secret": False},
            },
            "attachments": [file_payload],
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["variables"]["priority_hint"]["value"] == "high"
    assert len(body["attachments"]) == 1
    assert body["attachments"][0]["file_id"] == file_ref["file_id"]


async def test_create_empty_title_returns_422(worktracker_client) -> None:
    response = await worktracker_client.post(WORK_ITEMS, json={"title": ""})
    assert response.status_code == 422


async def test_patch_work_item_fields(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    work_item_id = create_resp.json()["work_item_id"]
    before_updated = create_resp.json()["updated_at"]

    patch_resp = await worktracker_client.patch(
        f"{WORK_ITEMS}/{work_item_id}",
        json={
            "title": f"Updated {unique_id}",
            "description": "desc",
            "labels": ["a"],
            "variables": {"x": {"value": "1", "visibility": "internal"}},
        },
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["title"] == f"Updated {unique_id}"
    assert body["description"] == "desc"
    assert body["labels"] == ["a"]
    assert body["updated_at"] != before_updated

    missing = await worktracker_client.patch(
        f"{WORK_ITEMS}/wi_missing_{unique_id}",
        json={"title": "x"},
    )
    assert missing.status_code == 404


async def test_assign_reassign_users(
    worktracker_client,
    system_user_id: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    work_item_id = create_resp.json()["work_item_id"]

    assign_resp = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/assign",
        json=build_users_assignment(system_user2_id),
    )
    assert assign_resp.status_code == 200
    assert system_user2_id in assign_resp.json()["assignment"]["user_ids"]


async def test_move_work_item_column(
    worktracker_client,
    worktracker_board,
    unique_id: str,
) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id),
            "board_id": worktracker_board.board_id,
            "board_column_id": "todo",
        },
    )
    work_item_id = create_resp.json()["work_item_id"]

    move_resp = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/move",
        json={"board_column_id": "done"},
    )
    assert move_resp.status_code == 200
    body = move_resp.json()
    assert body["board_column_id"] == "done"
    assert body["state"] == "done"

    bad_move = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/move",
        json={"board_column_id": "missing"},
    )
    assert bad_move.status_code == 400


async def test_claim_queue_item(
    worktracker_client,
    worktracker_queue,
    system_user_id: str,
    unique_id: str,
) -> None:
    queue_id = worktracker_queue.work_queue_id
    await worktracker_client.post(
        f"{API_PREFIX}/work-queues/{queue_id}/members",
        json={"member": {"actor_kind": "user", "user_id": system_user_id}, "role": "member"},
    )
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id),
            **build_queue_assignment(queue_id),
        },
    )
    work_item_id = create_resp.json()["work_item_id"]

    claim_resp = await worktracker_client.post(f"{WORK_ITEMS}/{work_item_id}/claim")
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["state"] == "in_progress"
    assert body["assignment"]["claimed_by_user_id"] == system_user_id


async def test_claim_by_non_member_returns_403(
    worktracker_client,
    worktracker_queue,
    auth_headers_system_user2,
    unique_id: str,
) -> None:
    queue_id = worktracker_queue.work_queue_id
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id),
            **build_queue_assignment(queue_id),
        },
    )
    work_item_id = create_resp.json()["work_item_id"]

    claim_resp = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/claim",
        headers=auth_headers_system_user2,
    )
    assert claim_resp.status_code == 403


async def test_comments_create_and_list(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    work_item_id = create_resp.json()["work_item_id"]

    comment_resp = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/comments",
        json={"text": f"Note {unique_id}"},
    )
    assert comment_resp.status_code == 201
    comment = comment_resp.json()
    assert comment["text"] == f"Note {unique_id}"

    list_resp = await worktracker_client.get(f"{WORK_ITEMS}/{work_item_id}/comments")
    assert list_resp.status_code == 200
    comments = list_resp.json()
    assert len(comments) >= 1
    assert comments[0]["text"] == f"Note {unique_id}"


async def test_complete_and_cancel_work_item(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id, title=f"Complete {unique_id}"),
    )
    work_item_id = create_resp.json()["work_item_id"]

    complete_resp = await worktracker_client.post(
        f"{WORK_ITEMS}/{work_item_id}/complete",
        json={"resolution_text": "resolved"},
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["state"] == "done"
    assert complete_resp.json()["resolution"]["text"] == "resolved"

    create2 = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id, title=f"Cancel {unique_id}"),
    )
    cancel_id = create2.json()["work_item_id"]
    cancel_resp = await worktracker_client.post(f"{WORK_ITEMS}/{cancel_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == "cancelled"


async def test_list_queue_unclaimed_only(
    worktracker_client,
    worktracker_queue,
    unique_id: str,
) -> None:
    queue_id = worktracker_queue.work_queue_id
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json={
            **build_manual_work_item_payload(unique_id),
            **build_queue_assignment(queue_id),
        },
    )
    work_item_id = create_resp.json()["work_item_id"]

    unclaimed = await worktracker_client.get(
        WORK_ITEMS,
        params={"queue_unclaimed_only": True, "work_queue_id": queue_id},
    )
    assert unclaimed.status_code == 200
    ids = {item["work_item_id"] for item in unclaimed.json()["items"]}
    assert work_item_id in ids
