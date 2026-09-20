"""HTTP REST /worktracker/api/v1/work-queues."""

from __future__ import annotations

import pytest

from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.assertions import assert_items_object, assert_offset_page
from tests.worktracker.helpers.builders import build_queue_payload

pytestmark = pytest.mark.asyncio

QUEUES = f"{API_PREFIX}/work-queues"


async def test_list_queues_empty_then_populated(worktracker_client, unique_id: str) -> None:
    before = await worktracker_client.get(QUEUES)
    assert before.status_code == 200
    assert_offset_page(before.json())

    create_resp = await worktracker_client.post(QUEUES, json=build_queue_payload(unique_id))
    assert create_resp.status_code == 201

    after = await worktracker_client.get(QUEUES)
    assert after.status_code == 200
    slugs = {item["work_queue_slug"] for item in after.json()["items"]}
    assert f"q-{unique_id}" in slugs


async def test_create_queue_duplicate_slug_returns_409(worktracker_client, unique_id: str) -> None:
    payload = build_queue_payload(unique_id)
    first = await worktracker_client.post(QUEUES, json=payload)
    assert first.status_code == 201

    second = await worktracker_client.post(QUEUES, json=payload)
    assert second.status_code == 409


async def test_update_queue(worktracker_client, worktracker_queue) -> None:
    queue_id = worktracker_queue.work_queue_id
    response = await worktracker_client.patch(
        f"{QUEUES}/{queue_id}",
        json={"name": "Renamed queue", "description": "desc"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed queue"
    assert body["description"] == "desc"


async def test_update_queue_without_admin_returns_403(
    worktracker_client_company2, worktracker_queue
) -> None:
    response = await worktracker_client_company2.patch(
        f"{QUEUES}/{worktracker_queue.work_queue_id}",
        json={"name": "Nope"},
    )
    assert response.status_code == 403


async def test_queue_members_add_list_remove(
    worktracker_client,
    worktracker_queue,
    system_user2_id: str,
) -> None:
    queue_id = worktracker_queue.work_queue_id
    member_user_id = system_user2_id
    add_resp = await worktracker_client.post(
        f"{QUEUES}/{queue_id}/members",
        json={"member": {"actor_kind": "user", "user_id": member_user_id}, "role": "member"},
    )
    assert add_resp.status_code == 201

    list_resp = await worktracker_client.get(f"{QUEUES}/{queue_id}/members")
    assert list_resp.status_code == 200
    members = assert_items_object(list_resp.json())
    assert any(m["member"]["user_id"] == member_user_id for m in members)

    remove_resp = await worktracker_client.post(
        f"{QUEUES}/{queue_id}/members/remove",
        json={"member": {"actor_kind": "user", "user_id": member_user_id}},
    )
    assert remove_resp.status_code == 204

    list_after = await worktracker_client.get(f"{QUEUES}/{queue_id}/members")
    assert not any(
        m["member"]["user_id"] == member_user_id for m in assert_items_object(list_after.json())
    )


async def test_delete_queue_removes_access(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(QUEUES, json=build_queue_payload(unique_id))
    assert create_resp.status_code == 201
    queue_id = create_resp.json()["work_queue_id"]

    deleted = await worktracker_client.delete(f"{QUEUES}/{queue_id}")
    assert deleted.status_code == 204

    members = await worktracker_client.get(f"{QUEUES}/{queue_id}/members")
    assert members.status_code == 403

    listed = await worktracker_client.get(QUEUES)
    slugs = {item["work_queue_slug"] for item in listed.json()["items"]}
    assert f"q-{unique_id}" not in slugs


async def test_remove_unknown_member_returns_404(worktracker_client, worktracker_queue) -> None:
    queue_id = worktracker_queue.work_queue_id
    response = await worktracker_client.post(
        f"{QUEUES}/{queue_id}/members/remove",
        json={"member": {"actor_kind": "user", "user_id": "user_unknown_999"}},
    )
    assert response.status_code == 404
