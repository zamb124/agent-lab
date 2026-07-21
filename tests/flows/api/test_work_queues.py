"""HTTP REST /flows/api/v1/work-queues (HITL editor picker)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

QUEUES = "/flows/api/v1/work-queues"


async def test_list_queues_empty_then_populated(client, unique_id: str) -> None:
    before = await client.get(QUEUES)
    assert before.status_code == 200
    body_before = before.json()
    assert isinstance(body_before["items"], list)
    assert body_before["total"] == len(body_before["items"])

    slug = f"hitl-q-{unique_id}"
    create_resp = await client.post(
        QUEUES,
        json={"name": f"HITL Queue {unique_id}", "slug": slug},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["work_queue_slug"] == slug
    assert created["name"] == f"HITL Queue {unique_id}"
    assert isinstance(created["work_queue_id"], str)
    assert created["work_queue_id"].startswith("wq_")

    after = await client.get(QUEUES)
    assert after.status_code == 200
    slugs = {item["work_queue_slug"] for item in after.json()["items"]}
    assert slug in slugs


async def test_create_queue_duplicate_slug_returns_409(client, unique_id: str) -> None:
    payload = {"name": f"Dup {unique_id}", "slug": f"dup-{unique_id}"}
    first = await client.post(QUEUES, json=payload)
    assert first.status_code == 201

    second = await client.post(QUEUES, json=payload)
    assert second.status_code == 409


async def test_create_queue_adds_creator_as_owner(
    client,
    container,
    system_user_id: str,
    unique_id: str,
) -> None:
    slug = f"owner-q-{unique_id}"
    create_resp = await client.post(
        QUEUES,
        json={"name": f"Owner Queue {unique_id}", "slug": slug},
    )
    assert create_resp.status_code == 201
    queue_id = create_resp.json()["work_queue_id"]

    members = await container.work_item_service.list_queue_members(queue_id)
    owner_ids = [
        m.member.user_id
        for m in members
        if m.role == "owner" and getattr(m.member, "user_id", None) is not None
    ]
    assert system_user_id in owner_ids
