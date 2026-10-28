"""Заявки на доступ: смена resource_id и повторные pending."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.crm.models.access_request import AccessRequest


def _request(
    *,
    access_request_id: str,
    company_id: str,
    requester_id: str,
    resource_id: str,
    created_at: datetime,
    status: str = "pending",
) -> AccessRequest:
    return AccessRequest(
        access_request_id=access_request_id,
        company_id=company_id,
        requester_id=requester_id,
        requester_company_id=company_id,
        owner_id=f"owner-{company_id}",
        resource_type="entity",
        resource_id=resource_id,
        created_at=created_at,
        updated_at=created_at,
        status=status,
    )


@pytest.mark.asyncio
async def test_update_entity_resource_id_counts_company_rows(unique_id: str) -> None:
    company_id = f"ar-{unique_id}"
    other_company_id = f"ar-other-{unique_id}"
    source_id = f"src-{unique_id}"
    survivor_id = f"surv-{unique_id}"
    now = datetime(2024, 1, 1, tzinfo=UTC)
    _ = await AccessRequest.create(
        _request(
            access_request_id=f"ar-home-{unique_id}",
            company_id=company_id,
            requester_id=f"user-{unique_id}",
            resource_id=source_id,
            created_at=now,
        )
    )
    _ = await AccessRequest.create(
        _request(
            access_request_id=f"ar-foreign-{unique_id}",
            company_id=other_company_id,
            requester_id=f"user-{unique_id}",
            resource_id=source_id,
            created_at=now,
        )
    )

    assert await AccessRequest.update_entity_resource_id(company_id, source_id, survivor_id) == 1
    assert await AccessRequest.update_entity_resource_id(company_id, source_id, survivor_id) == 0


@pytest.mark.asyncio
async def test_delete_duplicate_pending_keeps_earliest_requester(unique_id: str) -> None:
    company_id = f"ar-dup-{unique_id}"
    entity_id = f"ent-{unique_id}"
    early = datetime(2024, 1, 1, tzinfo=UTC)
    late = early + timedelta(hours=1)
    _ = await AccessRequest.create(
        _request(
            access_request_id=f"ar-early-{unique_id}",
            company_id=company_id,
            requester_id="same",
            resource_id=entity_id,
            created_at=early,
        )
    )
    _ = await AccessRequest.create(
        _request(
            access_request_id=f"ar-late-{unique_id}",
            company_id=company_id,
            requester_id="same",
            resource_id=entity_id,
            created_at=late,
        )
    )
    _ = await AccessRequest.create(
        _request(
            access_request_id=f"ar-other-user-{unique_id}",
            company_id=company_id,
            requester_id="other",
            resource_id=entity_id,
            created_at=late,
        )
    )

    await AccessRequest.delete_duplicate_pending_for_entity(entity_id)
    left = await AccessRequest.objects.filter(resource_id=entity_id, status="pending").all()
    assert {row.access_request_id for row in left} == {
        f"ar-early-{unique_id}",
        f"ar-other-user-{unique_id}",
    }
