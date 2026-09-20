"""Ingest bus: persist, XADD, идемпотентность, GET /events, изоляция чтения."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fixtures.platform_events import platform_events_listener
from tests.realtime.bus_events import bus_notify_event
from tests.realtime.centrifugo_ws import (
    assert_no_platform_event,
    connect_centrifugo,
    wait_platform_event,
)


@pytest.mark.asyncio
async def test_ingest_persists_xadd_and_get_event(
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    event_id = f"e_ing_{unique_id}"
    title = f"ingest-{unique_id}"
    body = bus_notify_event(
        event_id=event_id,
        user_id=system_user_id,
        title=title,
    )
    async with platform_events_listener() as receive:
        async with connect_centrifugo(auth_token_system) as ws:
            posted = await realtime_session_client.post(
                "/realtime/api/v1/internal/events",
                json=body,
            )
            assert posted.status_code == 200, posted.text
            stored = posted.json()
            assert stored["event_id"] == event_id
            assert stored["type"] == "notify/test/system_received"
            frame = await wait_platform_event(
                ws,
                type_="notify/test/system_received",
                where={"title": title},
                timeout=10.0,
            )
            assert frame["event_id"] == event_id
            assert "delivery" not in frame
            fetched = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
            assert fetched.status_code == 200, fetched.text
            snapshot = fetched.json()
            assert snapshot["event_id"] == event_id
            assert snapshot["payload"]["title"] == title
        stream_events = await receive("notify/test/system_received", system_user_id, 5.0)
        matched = [item for item in stream_events if item.get("event_id") == event_id]
        assert len(matched) == 1
        assert matched[0]["delivery"]["user_ids"] == [system_user_id]


@pytest.mark.asyncio
async def test_ingest_same_event_id_is_idempotent(
    realtime_session_client: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    event_id = f"e_idem_{unique_id}"
    first = bus_notify_event(
        event_id=event_id,
        user_id=system_user_id,
        title=f"first-{unique_id}",
    )
    second = bus_notify_event(
        event_id=event_id,
        user_id=system_user_id,
        title=f"second-{unique_id}",
    )
    created = await realtime_session_client.post(
        "/realtime/api/v1/internal/events",
        json=first,
    )
    assert created.status_code == 200, created.text
    repeated = await realtime_session_client.post(
        "/realtime/api/v1/internal/events",
        json=second,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["payload"]["title"] == f"first-{unique_id}"
    fetched = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert fetched.json()["payload"]["title"] == f"first-{unique_id}"


@pytest.mark.asyncio
async def test_get_event_requires_session(
    realtime_client_http: AsyncClient,
    unique_id: str,
) -> None:
    response = await realtime_client_http.get(f"/realtime/api/v1/events/e_missing_{unique_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_event_unknown_is_404(
    realtime_session_client: AsyncClient,
    unique_id: str,
) -> None:
    response = await realtime_session_client.get(f"/realtime/api/v1/events/e_missing_{unique_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_event_hidden_from_other_user(
    realtime_session_client: AsyncClient,
    realtime_session_client_user2: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    event_id = f"e_priv_{unique_id}"
    posted = await realtime_session_client.post(
        "/realtime/api/v1/internal/events",
        json=bus_notify_event(
            event_id=event_id,
            user_id=system_user_id,
            title=f"private-{unique_id}",
        ),
    )
    assert posted.status_code == 200, posted.text
    other = await realtime_session_client_user2.get(f"/realtime/api/v1/events/{event_id}")
    assert other.status_code == 404
    own = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert own.status_code == 200


@pytest.mark.asyncio
async def test_domain_event_is_logged_not_on_ws(
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    event_id = f"e_dom_{unique_id}"
    marker = f"domain-{unique_id}"
    async with connect_centrifugo(auth_token_system) as ws:
        posted = await realtime_session_client.post(
            "/realtime/api/v1/internal/events",
            json={
                "event_id": event_id,
                "type": "crm/entity/created",
                "company_id": "system",
                "payload": {"entity_id": marker},
                "meta": {"source": "system", "actor_user_id": system_user_id},
            },
        )
        assert posted.status_code == 200, posted.text
        await assert_no_platform_event(
            ws,
            type_="crm/entity/created",
            duration=1.2,
            where={"entity_id": marker},
        )
    fetched = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert fetched.status_code == 200, fetched.text
    snapshot = fetched.json()
    assert snapshot["payload"]["entity_id"] == marker
    assert snapshot.get("delivery") is None
