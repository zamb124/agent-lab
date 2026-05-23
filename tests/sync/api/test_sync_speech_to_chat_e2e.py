"""E2E speech-to-chat: реальный LiveKit + cli publisher → сегмент в ленту.

Цепочка:
  1. Канал topic с `speech_to_chat_enabled=True` (одиночный member: только owner).
  2. Owner делает `POST /calls/.../invite` → `len(member_ids) <= 1` →
     звонок сразу `active`, стартует `_maybe_start_speech_to_chat_poll` →
     TaskIQ `sync_speech_to_chat_poll_task` (реальный sync_worker).
  3. `livekit_demo_publisher(room_name=call.livekit_room_name)` — публикует
     фикстурный Opus-файл `tests/fixtures/sync/speech_demo.ogg` через
     контейнер `agentlab_livekit_cli_test`.
  4. Speech-to-chat poll создаёт track-egress на микрофон публикатора,
     egress пишет 2-секундные сегменты в MinIO `sync-speech/...`, воркер
     обрабатывает (silence detect/trim) и через `op_messages_send` от лица
     `participant_identity` публикует `file/audio` сообщение с
     `source_speech_to_chat=True`.

Без моков и monkeypatch: реальный sync_service, реальный sync_worker,
реальные LiveKit + egress + cli + MinIO (`make test-up`).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from core.utils.tokens import get_token_service
from tests.sync.api._helpers import seed_namespace_via_repo
from tests.sync.api._realtime_helpers import (
    http_owner,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(150)
async def test_speech_to_chat_posts_audio_segment_to_channel_feed(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    livekit_demo_publisher,
) -> None:
    namespace = await seed_namespace_via_repo(company_id, f"ns_{unique_id}_s2c")

    async with http_owner(sync_auth_token) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "speech_to_chat_ch",
                "is_private": False,
                "speech_to_chat_enabled": True,
            },
        )
        assert cr.status_code == 201, cr.text
        channel_id = cr.json()["channel_id"]

        invite = await http.post(
            "/sync/api/v1/calls/any/invite",
            json={"channel_id": channel_id},
        )
        assert invite.status_code == 200, invite.text
        call = invite.json()
        assert isinstance(call["livekit_room_name"], str) and call["livekit_room_name"] != ""

        gr = await http.get(f"/sync/api/v1/calls/{call['call_id']}")
        assert gr.status_code == 200, gr.text
        fresh = gr.json()
        assert fresh["status"] == "active"

    # Identity publisher'a должен совпадать с user_id владельца канала:
    # speech-to-chat workflow публикует `file/audio` сообщение от лица
    # `participant_identity`, а `_send_message` требует, чтобы sender был
    # участником канала. С чужим identity получили бы PermissionError.
    owner_user_id = _user_id_from_token(sync_auth_token)
    pub_identity = await livekit_demo_publisher(
        room_name=call["livekit_room_name"],
        settle_seconds=5.0,
        identity=owner_user_id,
    )

    deadline = asyncio.get_event_loop().time() + 90.0
    speech_message: dict | None = None
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:9005",
        timeout=10.0,
        headers={"Authorization": f"Bearer {sync_auth_token}"},
    ) as long_http:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await long_http.get(f"/sync/api/v1/channels/{channel_id}/messages?limit=50")
            except (
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.ConnectError,
                httpx.ReadTimeout,
            ):
                await asyncio.sleep(2.0)
                continue
            if r.status_code != 200:
                await asyncio.sleep(2.0)
                continue
            items = r.json()["items"]
            for msg in items:
                if msg.get("call_id") != call["call_id"]:
                    continue
                for content in msg.get("contents", []):
                    if content.get("type") != "file/audio":
                        continue
                    if content.get("data", {}).get("source_speech_to_chat") is True:
                        speech_message = msg
                        break
                if speech_message is not None:
                    break
            if speech_message is not None:
                break
            await asyncio.sleep(2.0)

    assert speech_message is not None, (
        f"Speech-to-chat сегмент не появился в ленте за 90с (publisher identity={pub_identity}, "
        f"room={call['livekit_room_name']}, channel={channel_id})."
    )

    audio = next(c for c in speech_message["contents"] if c["type"] == "file/audio")
    assert audio["data"]["source_speech_to_chat"] is True
    assert audio["data"].get("file_id"), "speech-to-chat сегмент должен иметь file_id"
    assert speech_message["sender"]["user_id"] == pub_identity, (
        "Сообщение публикуется от лица participant_identity (publisher)."
    )

    async with http_owner(sync_auth_token) as http:
        await http.post(f"/sync/api/v1/calls/{call['call_id']}/hangup")
