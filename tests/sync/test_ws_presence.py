"""Presence: онлайн через Centrifugo после SESSION JWT connect."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from core.realtime.presence import is_user_connected
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo
from tests.sync.api._realtime_helpers import wait_sync_ws_offline, wait_sync_ws_online


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_sync_ws_presence_online_after_centrifugo_connect(
    sync_service,
    realtime_service,
    sync_auth_token,
    company_id: str,
) -> None:
    token_data = get_token_service().validate_token(sync_auth_token)
    if token_data is None:
        raise AssertionError("invalid SESSION JWT")
    uid = token_data.user_id
    assert await is_user_connected(uid, company_id=company_id) is False
    async with connect_centrifugo(sync_auth_token) as ws:
        _ = ws
        assert await is_user_connected(uid, company_id=company_id) is True
    assert await is_user_connected(uid, company_id=company_id) is False


def _member_row(items: object, user_id: str) -> dict[str, object]:
    if not isinstance(items, list):
        raise AssertionError("company members items must be list")
    for row in items:
        if not isinstance(row, dict):
            raise AssertionError("company member row must be object")
        if row.get("user_id") == user_id:
            return row
    raise AssertionError(f"member {user_id!r} missing from company members")


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_company_members_is_online_from_centrifugo(
    sync_service,
    realtime_service,
    sync_client: AsyncClient,
    sync_auth_headers: dict[str, str],
    sync_auth_token_user2: str,
    sync_user2_id: str,
    company_id: str,
) -> None:
    _ = sync_service
    _ = realtime_service
    before = await sync_client.get("/sync/api/v1/company/members", headers=sync_auth_headers)
    assert before.status_code == 200, before.text
    offline_row = _member_row(before.json()["items"], sync_user2_id)
    assert offline_row["is_online"] is False

    async with connect_centrifugo(sync_auth_token_user2) as ws:
        _ = ws
        await wait_sync_ws_online(sync_user2_id, company_id=company_id)
        online = await sync_client.get("/sync/api/v1/company/members", headers=sync_auth_headers)
        assert online.status_code == 200, online.text
        online_row = _member_row(online.json()["items"], sync_user2_id)
        assert online_row["is_online"] is True
        assert online_row["last_seen_at"] is None

    await wait_sync_ws_offline(sync_user2_id, company_id=company_id)
    after = await sync_client.get("/sync/api/v1/company/members", headers=sync_auth_headers)
    assert after.status_code == 200, after.text
    after_row = _member_row(after.json()["items"], sync_user2_id)
    assert after_row["is_online"] is False
    last_seen = after_row["last_seen_at"]
    if not isinstance(last_seen, str) or last_seen == "":
        raise AssertionError(f"last_seen_at after disconnect must be ISO string, got {last_seen!r}")
