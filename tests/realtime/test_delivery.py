"""Адресация Centrifugo: user / company / broadcast — без пересечения каналов."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.realtime.bus_events import bus_notify_event
from tests.realtime.centrifugo_ws import (
    assert_no_platform_event,
    connect_centrifugo,
    wait_platform_event,
)


@pytest.mark.asyncio
async def test_user_channel_does_not_leak_to_peer(
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    auth_token_system_user2: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    title = f"only-owner-{unique_id}"
    event_id = f"e_user_{unique_id}"
    async with (
        connect_centrifugo(auth_token_system) as owner_ws,
        connect_centrifugo(auth_token_system_user2) as peer_ws,
    ):
        posted = await realtime_session_client.post(
            "/realtime/api/v1/internal/events",
            json=bus_notify_event(
                event_id=event_id,
                user_id=system_user_id,
                title=title,
            ),
        )
        assert posted.status_code == 200, posted.text
        frame = await wait_platform_event(
            owner_ws,
            type_="notify/test/system_received",
            where={"title": title},
            timeout=10.0,
        )
        assert frame["event_id"] == event_id
        await assert_no_platform_event(
            peer_ws,
            type_="notify/test/system_received",
            duration=1.2,
            where={"title": title},
        )


@pytest.mark.asyncio
async def test_company_channel_reaches_both_members(
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    auth_token_system_user2: str,
    unique_id: str,
) -> None:
    title = f"company-{unique_id}"
    event_id = f"e_co_{unique_id}"
    async with (
        connect_centrifugo(auth_token_system) as owner_ws,
        connect_centrifugo(auth_token_system_user2) as peer_ws,
    ):
        posted = await realtime_session_client.post(
            "/realtime/api/v1/internal/events",
            json={
                "event_id": event_id,
                "type": "notify/test/system_received",
                "company_id": "system",
                "payload": {
                    "title": title,
                    "message": title,
                    "kind": "system",
                    "service": "test",
                    "priority": "normal",
                },
                "meta": {"source": "system"},
                "delivery": {"company_id": "system"},
            },
        )
        assert posted.status_code == 200, posted.text
        owner_frame = await wait_platform_event(
            owner_ws,
            type_="notify/test/system_received",
            where={"title": title},
            timeout=10.0,
        )
        peer_frame = await wait_platform_event(
            peer_ws,
            type_="notify/test/system_received",
            where={"title": title},
            timeout=10.0,
        )
        assert owner_frame["event_id"] == peer_frame["event_id"] == event_id


@pytest.mark.asyncio
async def test_broadcast_reaches_both_connections(
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    auth_token_system_user2: str,
    unique_id: str,
) -> None:
    title = f"broadcast-{unique_id}"
    event_id = f"e_bc_{unique_id}"
    async with (
        connect_centrifugo(auth_token_system) as owner_ws,
        connect_centrifugo(auth_token_system_user2) as peer_ws,
    ):
        posted = await realtime_session_client.post(
            "/realtime/api/v1/internal/events",
            json={
                "event_id": event_id,
                "type": "notify/test/system_received",
                "company_id": "system",
                "payload": {
                    "title": title,
                    "message": title,
                    "kind": "system",
                    "service": "test",
                    "priority": "normal",
                },
                "meta": {"source": "system"},
                "delivery": {"broadcast": True},
            },
        )
        assert posted.status_code == 200, posted.text
        owner_frame = await wait_platform_event(
            owner_ws,
            type_="notify/test/system_received",
            where={"title": title},
            timeout=10.0,
        )
        peer_frame = await wait_platform_event(
            peer_ws,
            type_="notify/test/system_received",
            where={"title": title},
            timeout=10.0,
        )
        assert owner_frame["event_id"] == peer_frame["event_id"] == event_id
