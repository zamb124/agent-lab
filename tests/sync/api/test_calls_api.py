"""Интеграционные HTTP тесты REST API звонков.

Использует реальный sync ASGI + реальную БД. Без моков.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_turn_credentials_requires_auth(
    sync_client,
    sync_db_clean: None,
) -> None:
    """Endpoint TURN credentials требует авторизацию."""
    r = await sync_client.get("/sync/api/v1/calls/turn-credentials")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_turn_credentials_returns_structure(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    """TURN credentials возвращают корректную структуру — turn_host задан в conf.json."""
    r = await sync_client.get("/sync/api/v1/calls/turn-credentials", headers=auth_headers_system)
    assert r.status_code == 200
    data = r.json()
    assert "username" in data
    assert "credential" in data
    assert "uris" in data
    assert len(data["uris"]) == 3


@pytest.mark.asyncio
async def test_create_call_link_requires_auth(
    sync_client,
    sync_db_clean: None,
) -> None:
    r = await sync_client.post(
        "/sync/api/v1/calls/links",
        json={"channel_id": "fake", "call_type": "audio"},
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_call_link_invalid_channel(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    """Несуществующий канал → 403 (нет доступа)."""
    r = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={"channel_id": "nonexistent_channel_id", "call_type": "video"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_join_nonexistent_link_returns_404(
    sync_client,
    sync_db_clean: None,
) -> None:
    """Несуществующая ссылка → 404."""
    r = await sync_client.get("/sync/api/v1/calls/join/nonexistent_token_xyz_abc")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_join_link_post_without_guest_name_returns_error(
    sync_client,
    sync_db_clean: None,
) -> None:
    """POST на join без тела и без auth → 404 (ссылка не найдена)."""
    r = await sync_client.post("/sync/api/v1/calls/join/nonexistent_token_abc")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_call_not_found(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    """Несуществующий call_id → 404."""
    r = await sync_client.get(
        "/sync/api/v1/calls/nonexistent_call_id",
        headers=auth_headers_system,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_full_link_flow(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    """
    Полный flow: создание space → channel → ссылка → публичное чтение info.
    """
    space_r = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=auth_headers_system,
        json={"name": "CallTestSpace", "description": None},
    )
    assert space_r.status_code == 201
    space_id = space_r.json()["id"]

    ch_r = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=auth_headers_system,
        json={"name": "CallTestChannel", "type": "topic", "space_id": space_id},
    )
    assert ch_r.status_code == 201
    channel_id = ch_r.json()["id"]

    link_r = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={"channel_id": channel_id, "call_type": "video", "ttl_hours": 1},
    )
    assert link_r.status_code == 201
    link_data = link_r.json()
    assert "link_token" in link_data
    assert "join_url" in link_data
    assert link_data["channel_id"] == channel_id
    assert "/sync/join/" in link_data["join_url"]
    assert link_data["call_type"] == "video"

    token = link_data["link_token"]
    info_r = await sync_client.get(f"/sync/api/v1/calls/join/{token}")
    assert info_r.status_code == 200
    info = info_r.json()
    assert info["link_token"] == token
    assert info["call_type"] == "video"
    assert info["channel_name"] == "CallTestChannel"


@pytest.mark.asyncio
async def test_join_link_flow_registered_and_guest(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    """
    Полный flow: registered join + guest join + livekit token endpoint.

    Один space/channel/link создаётся один раз — оба входа переиспользуют
    одну LiveKit комнату. Умещается в 5s: одна пара TaskIQ-вызовов + LiveKit.
    """
    space_r = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=auth_headers_system,
        json={"name": "JoinFlowSpace", "description": None},
    )
    assert space_r.status_code == 201

    ch_r = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=auth_headers_system,
        json={"name": "JoinFlowChannel", "type": "topic", "space_id": space_r.json()["id"]},
    )
    assert ch_r.status_code == 201
    channel_id = ch_r.json()["id"]

    link_r = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={"channel_id": channel_id, "call_type": "video", "ttl_hours": 1},
    )
    assert link_r.status_code == 201
    token = link_r.json()["link_token"]

    # Зарегистрированный пользователь
    join_reg = await sync_client.post(
        f"/sync/api/v1/calls/join/{token}",
        headers=auth_headers_system,
    )
    assert join_reg.status_code == 200
    reg_data = join_reg.json()
    assert reg_data["mode"] == "sfu"
    assert not reg_data["identity"].startswith("guest:")
    call_id = reg_data["call_id"]

    # Гость переиспользует ту же комнату
    join_guest = await sync_client.post(
        f"/sync/api/v1/calls/join/{token}",
        json={"guest_name": "Гость"},
    )
    assert join_guest.status_code == 200
    guest_data = join_guest.json()
    assert guest_data["identity"].startswith("guest:")
    assert guest_data["call_id"] == call_id

    # GET token через authenticated endpoint
    token_r = await sync_client.get(
        f"/sync/api/v1/calls/{call_id}/token",
        headers=auth_headers_system,
    )
    assert token_r.status_code == 200
    assert "token" in token_r.json()
    assert "livekit_url" in token_r.json()

    # Статус звонка
    call_r = await sync_client.get(
        f"/sync/api/v1/calls/{call_id}",
        headers=auth_headers_system,
    )
    assert call_r.status_code == 200
    assert call_r.json()["status"] == "active"
