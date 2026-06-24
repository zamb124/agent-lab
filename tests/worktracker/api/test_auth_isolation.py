"""Изоляция компаний и auth для worktracker API."""

from __future__ import annotations

import pytest

from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.builders import build_manual_work_item_payload

pytestmark = pytest.mark.asyncio

WORK_ITEMS = f"{API_PREFIX}/work-items"


async def test_system_item_not_visible_in_company2(
    worktracker_client,
    worktracker_client_company2,
    unique_id: str,
) -> None:
    create_resp = await worktracker_client.post(
        WORK_ITEMS,
        json=build_manual_work_item_payload(unique_id),
    )
    assert create_resp.status_code == 201
    work_item_id = create_resp.json()["work_item_id"]

    get_company2 = await worktracker_client_company2.get(f"{WORK_ITEMS}/{work_item_id}")
    assert get_company2.status_code == 404


async def test_unauthenticated_request_rejected(worktracker_app, unique_id: str) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(WORK_ITEMS)
        assert response.status_code in {401, 403}

        create_resp = await client.post(
            WORK_ITEMS,
            json=build_manual_work_item_payload(unique_id),
        )
        assert create_resp.status_code in {401, 403}
