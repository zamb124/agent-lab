"""E2E-сценарии звонков sync через настоящий WebSocket + REST + Redis.

Все тесты идут через `sync_service` (uvicorn 127.0.0.1:9005) и реальный
TaskIQ worker. Никаких моков и monkeypatch. Push-фреймы валидируются
двумя способами:

  - WS-клиент(ы) — для проверки доставки конкретному получателю в реальном
    времени.
  - `ui_events_listener` — для проверки `target.user_id` в конверте
    `platform:ui_events` (например, `signal` адресован одному target,
    остальным НЕ должен прийти).

LiveKit для invite-цепочки реально создаёт SFU-комнату (`mode == 'sfu'`,
`P2P_MAX = 0` в `apps/sync/realtime/call_handlers.py`); тест не запускает
publisher, нам важна только серверная часть (звонок, push, маркер
`call/boundary`, права admin/recording, signal forward).
"""

from __future__ import annotations

import asyncio

import pytest

from core.utils.tokens import get_token_service

from tests.sync.api._helpers import (
    create_topic_channel_via_http,
    seed_namespace_via_repo,
)
from tests.sync.api._realtime_helpers import (
    add_member_via_http,
    add_third_user,
    assert_no_frame,
    connect_ws,
    http_owner,
    wait_frame,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


async def _create_channel_with_members(
    sync_auth_token: str,
    company_id: str,
    unique_id: str,
    *,
    suffix: str,
    extra_user_ids: list[str],
    channel_name: str,
) -> str:
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix=suffix,
            channel_name=channel_name,
        )
        for uid in extra_user_ids:
            await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=uid)
    return channel_id


async def _invite_call(token: str, channel_id: str) -> dict:
    async with http_owner(token) as http:
        r = await http.post(
            "/sync/api/v1/calls/any/invite",
            json={"channel_id": channel_id},
        )
    if r.status_code != 200:
        raise AssertionError(f"invite failed: {r.status_code} {r.text}")
    return r.json()


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_invite_publishes_incoming_to_other_member(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="callinv", extra_user_ids=[user2_id], channel_name="invite_ch",
    )

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        call = await _invite_call(sync_auth_token, channel_id)
        assert call["status"] == "ringing"
        assert isinstance(call["livekit_room_name"], str) and call["livekit_room_name"] != ""

        frame = await wait_frame(
            ws_user2,
            type_="sync/call/incoming",
            where=lambda p: p.get("call_id") == call["call_id"]
                and p.get("channel_id") == channel_id,
            timeout=15.0,
        )

    payload = frame["payload"]
    assert payload["initiator_user_id"] == _user_id_from_token(sync_auth_token)
    assert payload["incoming_channel_kind"] == "topic"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_invite_writes_call_boundary_started_to_feed(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="callbnd", extra_user_ids=[user2_id], channel_name="boundary_ch",
    )

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        call = await _invite_call(sync_auth_token, channel_id)

        frame = await wait_frame(
            ws_user2,
            type_="sync/message/created",
            where=lambda p: p.get("channel_id") == channel_id
                and p.get("call_id") == call["call_id"]
                and any(c.get("type") == "call/boundary" for c in p.get("contents", [])),
            timeout=15.0,
        )

    boundary = next(c for c in frame["payload"]["contents"] if c["type"] == "call/boundary")
    assert boundary["data"]["phase"] == "started"
    assert boundary["data"]["call_id"] == call["call_id"]

    async with http_owner(sync_auth_token) as http:
        r = await http.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    boundary_msgs = [
        m for m in items
        if any(c["type"] == "call/boundary" and c["data"]["phase"] == "started" for c in m["contents"])
    ]
    assert len(boundary_msgs) == 1
    assert boundary_msgs[0]["call_id"] == call["call_id"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_accept_changes_status_active_and_publishes_accepted(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="accept", extra_user_ids=[user2_id], channel_name="accept_ch",
    )
    call = await _invite_call(sync_auth_token, channel_id)

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token_user2) as http2:
            r = await http2.post(f"/sync/api/v1/calls/{call['call_id']}/accept")
            assert r.status_code == 200, r.text
            accepted = r.json()
            assert accepted["status"] == "active"
            assert any(p["user_id"] == user2_id and p["status"] == "joined" for p in accepted["participants"])

        frame = await wait_frame(
            ws_owner,
            type_="sync/call/accepted",
            where=lambda p: p.get("call_id") == call["call_id"] and p.get("user_id") == user2_id,
            timeout=15.0,
        )

    assert frame["payload"]["call_id"] == call["call_id"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_decline_publishes_declined_to_initiator(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="decline", extra_user_ids=[user2_id], channel_name="decline_ch",
    )
    call = await _invite_call(sync_auth_token, channel_id)

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token_user2) as http2:
            r = await http2.post(f"/sync/api/v1/calls/{call['call_id']}/decline")
            assert r.status_code == 204, r.text

        frame = await wait_frame(
            ws_owner,
            type_="sync/call/declined",
            where=lambda p: p.get("call_id") == call["call_id"] and p.get("user_id") == user2_id,
            timeout=15.0,
        )

    assert frame["payload"]["call_id"] == call["call_id"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180)
async def test_call_hangup_by_last_participant_writes_call_boundary_ended(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="hangup", extra_user_ids=[user2_id], channel_name="hangup_ch",
    )
    call = await _invite_call(sync_auth_token, channel_id)

    async with http_owner(sync_auth_token_user2) as http2:
        r = await http2.post(f"/sync/api/v1/calls/{call['call_id']}/accept")
        assert r.status_code == 200

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.post(f"/sync/api/v1/calls/{call['call_id']}/hangup")
            assert r.status_code == 200, r.text
        async with http_owner(sync_auth_token_user2) as http2:
            r2 = await http2.post(f"/sync/api/v1/calls/{call['call_id']}/hangup")
            assert r2.status_code == 200, r2.text

        ended_frame = await wait_frame(
            ws_user2,
            type_="sync/call/ended",
            where=lambda p: p.get("call_id") == call["call_id"],
            timeout=20.0,
        )

    assert ended_frame["payload"]["status"] == "ended"

    async with http_owner(sync_auth_token) as http:
        r = await http.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    ended_boundaries = [
        m for m in items
        if any(c["type"] == "call/boundary" and c["data"]["phase"] == "ended" for c in m["contents"])
    ]
    assert len(ended_boundaries) == 1
    assert ended_boundaries[0]["call_id"] == call["call_id"]
    ended_boundary = next(
        c
        for c in ended_boundaries[0]["contents"]
        if c["type"] == "call/boundary" and c["data"]["phase"] == "ended"
    )
    assert ended_boundary["data"]["has_recording"] is False


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_signal_forwards_to_target_user_only(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    ui_events_listener,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    user3_id = f"sync_user3_sig_{unique_id}"
    sync_auth_token_user3 = await add_third_user(company_id=company_id, user_id=user3_id)

    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="signal", extra_user_ids=[user2_id, user3_id], channel_name="signal_ch",
    )
    call = await _invite_call(sync_auth_token, channel_id)

    async with connect_ws(sync_auth_token_user2) as ws_user2, \
            connect_ws(sync_auth_token_user3) as ws_user3:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.post(
                f"/sync/api/v1/calls/{call['call_id']}/signal",
                json={
                    "target_user_id": user2_id,
                    "signal_type": "offer",
                    "data": {"sdp": "v=0", "tag": unique_id},
                },
            )
            assert r.status_code == 204, r.text

        signaled = await wait_frame(
            ws_user2,
            type_="sync/call/signaled",
            where=lambda p: p.get("call_id") == call["call_id"]
                and p.get("data", {}).get("tag") == unique_id,
            timeout=15.0,
        )
        await assert_no_frame(ws_user3, type_="sync/call/signaled", duration=2.0)

    assert signaled["payload"]["target_user_id"] == user2_id
    assert signaled["payload"]["sender_user_id"] == _user_id_from_token(sync_auth_token)
    assert signaled["payload"]["signal_type"] == "offer"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_admin_transfer_only_admin_can_change(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    channel_id = await _create_channel_with_members(
        sync_auth_token, company_id, unique_id,
        suffix="admin", extra_user_ids=[user2_id], channel_name="admin_ch",
    )
    call = await _invite_call(sync_auth_token, channel_id)
    async with http_owner(sync_auth_token_user2) as http2:
        r = await http2.post(f"/sync/api/v1/calls/{call['call_id']}/accept")
        assert r.status_code == 200

    async with http_owner(sync_auth_token_user2) as http2:
        r = await http2.post(
            f"/sync/api/v1/calls/{call['call_id']}/admin/transfer",
            json={"target_user_id": _user_id_from_token(sync_auth_token)},
        )
        assert r.status_code == 403

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.post(
                f"/sync/api/v1/calls/{call['call_id']}/admin/transfer",
                json={"target_user_id": user2_id},
            )
            assert r.status_code == 200, r.text
            updated = r.json()
            assert updated["created_by_user_id"] == user2_id

        frame = await wait_frame(
            ws_user2,
            type_="sync/call/admin_changed",
            where=lambda p: p.get("call_id") == call["call_id"]
                and p.get("created_by_user_id") == user2_id,
            timeout=15.0,
        )
    assert frame["payload"]["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_call_invite_with_solo_member_immediately_active(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Когда в канале единственный участник (только owner) — invite сразу `active`.

    `op_calls_invite` ветка `len(member_ids) <= 1`: переводит звонок в
    `active`, без необходимости accept'а.
    """
    namespace = await seed_namespace_via_repo(company_id, f"ns_{unique_id}_solo")
    async with http_owner(sync_auth_token) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            json={"namespace": namespace, "type": "topic", "name": "solo_ch", "is_private": False},
        )
        assert cr.status_code == 201, cr.text
        channel_id = cr.json()["id"]

    call = await _invite_call(sync_auth_token, channel_id)

    async with http_owner(sync_auth_token) as http:
        r = await http.get(f"/sync/api/v1/calls/{call['call_id']}")
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["status"] == "active"
    assert fresh["started_at"] is not None
