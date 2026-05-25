"""
Frontend leads API: typed storage contract and system-only cursor listing.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.frontend.models import LeadRequestRecord
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID

REQUEST_STORAGE_PREFIX = f"company:{SYSTEM_COMPANY_ID}:request:"


@pytest_asyncio.fixture
async def frontend_client_system(frontend_app, auth_token_system):
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token_system},
        follow_redirects=True,
    ) as client:
        yield client


def _storage_key(lead_request_id: str) -> str:
    return f"{REQUEST_STORAGE_PREFIX}{lead_request_id}"


def _record(lead_request_id: str, created_at: datetime) -> LeadRequestRecord:
    return LeadRequestRecord(
        lead_request_id=lead_request_id,
        contact_name=f"Lead {lead_request_id}",
        email=None,
        phone="+7 999 000 00 00",
        organization_name=f"Org {lead_request_id}",
        comment="Need a demo",
        job_title="CTO",
        headcount_range="50_199",
        interested_products=["agents", "crm"],
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_create_lead_rejects_legacy_payload(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        "/frontend/api/leads",
        json={
            "name": "Legacy Name",
            "email": "legacy@example.com",
            "company": "Legacy Org",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_lead_stores_canonical_record(
    frontend_client: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    response = await frontend_client.post(
        "/frontend/api/leads",
        json={
            "contact_name": f"Lead {unique_id}",
            "email": f"lead_{unique_id}@example.com",
            "phone": None,
            "organization_name": f"Org {unique_id}",
            "job_title": "CTO",
            "headcount_range": "1_49",
            "interested_products": ["agents"],
            "comment": "Call me",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "id" not in body
    lead_request_id = body["lead_request_id"]
    key = _storage_key(lead_request_id)
    try:
        raw = await frontend_container.shared_storage.get(key, force_global=True)
        assert raw is not None
        stored = LeadRequestRecord.model_validate_json(raw)
        assert stored.lead_request_id == lead_request_id
        assert stored.contact_name == f"Lead {unique_id}"
        assert stored.organization_name == f"Org {unique_id}"
    finally:
        await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_list_lead_requests_forbidden_for_non_system(frontend_client_with_auth: AsyncClient) -> None:
    response = await frontend_client_with_auth.get("/frontend/api/lead-requests")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_lead_requests_system_cursor_page(
    frontend_client_system: AsyncClient,
    frontend_container,
    unique_id: str,
) -> None:
    newer_id = f"lead_new_{unique_id}"
    older_id = f"lead_old_{unique_id}"
    base = datetime(2100, 1, 1, tzinfo=timezone.utc)
    newer = _record(newer_id, base + timedelta(seconds=1))
    older = _record(older_id, base)
    try:
        _ = await frontend_container.shared_storage.set(
            _storage_key(newer_id),
            newer.model_dump_json(),
            force_global=True,
        )
        _ = await frontend_container.shared_storage.set(
            _storage_key(older_id),
            older.model_dump_json(),
            force_global=True,
        )

        first = await frontend_client_system.get(
            "/frontend/api/lead-requests",
            params={"limit": 1},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["items"][0]["lead_request_id"] == newer_id
        assert first_body["has_more"] is True
        assert first_body["next_cursor"] is not None

        second = await frontend_client_system.get(
            "/frontend/api/lead-requests",
            params={"limit": 1, "cursor": first_body["next_cursor"]},
        )
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["items"][0]["lead_request_id"] == older_id
    finally:
        await frontend_container.shared_storage.delete(_storage_key(newer_id), force_global=True)
        await frontend_container.shared_storage.delete(_storage_key(older_id), force_global=True)
