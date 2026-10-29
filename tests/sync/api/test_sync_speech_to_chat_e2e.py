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
     egress пишет 2-секундные сегменты в S3 `sync-speech/...`, воркер
     обрабатывает (silence detect/trim) и через `op_messages_send` от лица
     `participant_identity` публикует `file/audio` сообщение с
     `source_speech_to_chat=True`.

Без моков и monkeypatch: реальный sync_service, реальный sync_worker,
реальные LiveKit + egress + cli + S3 (`make test-up`).
"""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from core.utils.tokens import get_token_service
from tests.sync.api._helpers import seed_namespace_via_repo
from tests.sync.api._realtime_helpers import (
    http_owner,
)
from tests.sync.conftest import require_sync_di


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
    namespace = await seed_namespace_via_repo(require_sync_di(), company_id, f"ns_{unique_id}_s2c")

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
    speech_message: dict[str, object] | None = None
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:9005",
        timeout=10.0,
        headers={"Authorization": f"Bearer {sync_auth_token}"},
    ) as long_http:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await long_http.get(f"/sync/api/v1/channels/{channel_id}/messages?limit=50")
            except (
                httpx2.RemoteProtocolError,
                httpx2.ReadError,
                httpx2.ConnectError,
                httpx2.ReadTimeout,
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

    contents_raw = speech_message.get("contents")
    assert isinstance(contents_raw, list)
    audio: dict[str, object] | None = None
    for content in contents_raw:
        if not isinstance(content, dict):
            continue
        if content.get("type") != "file/audio":
            continue
        audio = content
        break
    assert audio is not None
    audio_data = audio.get("data")
    assert isinstance(audio_data, dict)
    assert audio_data.get("source_speech_to_chat") is True
    assert audio_data.get("file_id"), "speech-to-chat сегмент должен иметь file_id"
    sender_raw = speech_message.get("sender")
    assert isinstance(sender_raw, dict)
    assert sender_raw.get("user_id") == pub_identity, (
        "Сообщение публикуется от лица participant_identity (publisher)."
    )

    message_id = speech_message.get("message_id")
    assert isinstance(message_id, str) and message_id != ""
    stt_deadline = asyncio.get_event_loop().time() + 60.0
    speech_text: dict[str, object] | None = None
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:9005",
        timeout=10.0,
        headers={"Authorization": f"Bearer {sync_auth_token}"},
    ) as stt_http:
        while asyncio.get_event_loop().time() < stt_deadline:
            listed = await stt_http.get(
                f"/sync/api/v1/channels/{channel_id}/messages?limit=50"
            )
            if listed.status_code != 200:
                await asyncio.sleep(1.0)
                continue
            for msg in listed.json()["items"]:
                if msg.get("message_id") != message_id:
                    continue
                for content in msg.get("contents", []):
                    if content.get("type") != "text/plain":
                        continue
                    data = content.get("data")
                    if not isinstance(data, dict):
                        continue
                    if data.get("origin") == "speech" and isinstance(data.get("body"), str):
                        if data["body"].strip() != "":
                            speech_text = data
                            break
            if speech_text is not None:
                break
            await asyncio.sleep(1.0)
    assert speech_text is not None, (
        "После STT у speech-to-chat сегмента должен появиться text/plain origin=speech"
    )
    body_text = speech_text.get("body")
    assert isinstance(body_text, str)
    assert "Тестовая транскрипция" in body_text

    async with http_owner(sync_auth_token) as http:
        await http.post(f"/sync/api/v1/calls/{call['call_id']}/hangup")
