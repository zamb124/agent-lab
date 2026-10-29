"""Presence: HTTP bus → Centrifugo presence_stats, изолированный user_id."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from core.realtime.presence import fetch_user_presence, fetch_users_presence, is_user_connected
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo


@pytest.mark.asyncio
async def test_presence_http_requires_auth(
    realtime_client_http: AsyncClient,
    unique_id: str,
) -> None:
    response = await realtime_client_http.get(
        f"/realtime/api/v1/internal/presence/users/pres_{unique_id}"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_presence_offline_then_online_then_offline(
    realtime_session_client: AsyncClient,
    unique_id: str,
) -> None:
    user_id = f"pres_{unique_id}"
    token = get_token_service().create_token(user_id, company_id="system")
    assert await is_user_connected(user_id, company_id="system") is False
    offline = await realtime_session_client.get(
        f"/realtime/api/v1/internal/presence/users/{user_id}"
    )
    assert offline.status_code == 200, offline.text
    assert offline.json()["connected"] is False
    assert offline.json()["num_clients"] == 0
    async with (
        connect_centrifugo(token) as ws1,
        connect_centrifugo(token) as ws2,
    ):
        _ = ws1, ws2
        snapshot = await fetch_user_presence(user_id, company_id="system")
        assert snapshot.connected is True
        assert snapshot.num_clients >= 2
        http_online = await realtime_session_client.get(
            f"/realtime/api/v1/internal/presence/users/{user_id}"
        )
        assert http_online.status_code == 200, http_online.text
        assert http_online.json()["connected"] is True
        assert http_online.json()["num_clients"] >= 2
        batch = await fetch_users_presence([user_id], company_id="system")
        assert len(batch.items) == 1
        assert batch.items[0].connected is True
        batch_http = await realtime_session_client.post(
            "/realtime/api/v1/internal/presence/users",
            json={"user_ids": [user_id]},
        )
        assert batch_http.status_code == 200, batch_http.text
        items = batch_http.json()["items"]
        assert items[0]["connected"] is True
    assert await is_user_connected(user_id, company_id="system") is False
