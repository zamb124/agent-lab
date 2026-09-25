"""Idempotency of demo HITL queue ensure under company-init races."""

from __future__ import annotations

import asyncio

import pytest

from apps.flows.src.services.hitl_demo_queue import (
    EXAMPLE_HITL_SLUG,
    ensure_example_hitl_queue,
)
from core.worktracker.models import UserActor

pytestmark = pytest.mark.asyncio


async def test_ensure_example_hitl_queue_is_idempotent_when_called_twice(
    di, unique_id: str
) -> None:
    company_id = f"hitl_demo_{unique_id}"
    owner_id = f"owner_{unique_id}"
    extra_id = f"admin_{unique_id}"
    svc = di.work_item_service

    await ensure_example_hitl_queue(
        svc, company_id, member_user_ids=[owner_id, extra_id]
    )
    await ensure_example_hitl_queue(
        svc, company_id, member_user_ids=[owner_id, extra_id]
    )

    queue = await svc.get_queue_by_slug(company_id, EXAMPLE_HITL_SLUG)
    assert queue.company_id == company_id
    assert queue.work_queue_slug == EXAMPLE_HITL_SLUG
    assert await svc.is_member(queue.work_queue_id, UserActor(user_id=owner_id))
    assert await svc.is_member(queue.work_queue_id, UserActor(user_id=extra_id))


async def test_ensure_example_hitl_queue_survives_parallel_creates(
    di, unique_id: str
) -> None:
    company_id = f"hitl_demo_p_{unique_id}"
    owner_id = f"owner_{unique_id}"
    extra_id = f"admin_{unique_id}"
    svc = di.work_item_service

    await asyncio.gather(
        ensure_example_hitl_queue(
            svc, company_id, member_user_ids=[owner_id, extra_id]
        ),
        ensure_example_hitl_queue(
            svc, company_id, member_user_ids=[owner_id, extra_id]
        ),
        ensure_example_hitl_queue(
            svc, company_id, member_user_ids=[owner_id, extra_id]
        ),
    )

    queue = await svc.get_queue_by_slug(company_id, EXAMPLE_HITL_SLUG)
    assert queue.company_id == company_id
    members = await svc.list_queue_members(queue.work_queue_id)
    member_ids = {
        member.member.user_id
        for member in members
        if isinstance(member.member, UserActor)
    }
    assert member_ids == {owner_id, extra_id}
