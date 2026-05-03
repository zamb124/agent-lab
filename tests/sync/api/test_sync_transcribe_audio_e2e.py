"""E2E на ручную транскрипцию аудио (REST + WS).

Дополняет [`test_channel_voice_transcribe_flag.py`](test_channel_voice_transcribe_flag.py),
где проверен авто-путь по флагу канала. Здесь — явный POST .../transcribe
и WS-команда `sync/messages/transcribe_audio_requested`.

Без моков: реальный sync_service, sync_worker, mock STT (`VOICE__STT__PROVIDER=mock`)
через env. Push-фреймы валидируются у user2 через WebSocket.
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from typing import Any

import pytest

from core.utils.tokens import get_token_service

from tests.fixtures.audio_bytes import minimal_wav_silence
from tests.sync.api._helpers import create_topic_channel_via_http
from tests.sync.api._realtime_helpers import (
    add_member_via_http,
    connect_ws,
    http_owner,
    wait_frame,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


def _audio_content_block(file_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "file/audio",
        "order": 0,
        "data": {
            "file_id": file_payload["file_id"],
            "filename": "note.wav",
            "mime_type": "audio/wav",
            "size": file_payload["file_size"],
            "duration_ms": 800,
        },
    }


async def _upload_voice_and_send(
    token: str, channel_id: str
) -> tuple[str, dict[str, Any]]:
    wav = minimal_wav_silence(duration_sec=0.05)
    async with http_owner(token) as http:
        up = await http.post(
            "/sync/api/v1/files/",
            files={"file": ("note.wav", io.BytesIO(wav), "audio/wav")},
        )
        assert up.status_code == 200, up.text
        f = up.json()
        sr = await http.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            json={
                "thread_id": None,
                "parent_message_id": None,
                "contents": [_audio_content_block(f)],
            },
        )
        assert sr.status_code == 201, sr.text
    msg = sr.json()
    audio_block = next(c for c in msg["contents"] if c["type"] == "file/audio")
    assert audio_block["data"]["transcription_status"] == "idle", (
        "Без флага канала и без явного transcribe сообщение должно быть idle"
    )
    return msg["id"], msg


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_transcribe_audio_rest_marks_done_via_worker(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """REST `POST .../messages/{id}/transcribe` → processing → done через worker."""
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="trrest",
            channel_name="trrest_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)

    message_id, _ = await _upload_voice_and_send(sync_auth_token, channel_id)

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            tx = await http.post(
                f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/transcribe",
            )
            assert tx.status_code == 200, tx.text
            tx_msg = tx.json()
            tx_audio = next(c for c in tx_msg["contents"] if c["type"] == "file/audio")
            assert tx_audio["data"]["transcription_status"] == "processing"

        # processing-апдейт публикуется op'ом
        await wait_frame(
            ws_user2,
            type_="sync/message/updated",
            where=lambda p: p.get("id") == message_id and any(
                c["type"] == "file/audio" and c.get("data", {}).get("transcription_status") == "processing"
                for c in p.get("contents", [])
            ),
            timeout=10.0,
        )
        # done-апдейт публикуется воркером
        done_frame = await wait_frame(
            ws_user2,
            type_="sync/message/updated",
            where=lambda p: p.get("id") == message_id and any(
                c["type"] == "file/audio" and c.get("data", {}).get("transcription_status") == "done"
                for c in p.get("contents", [])
            ),
            timeout=60.0,
        )

    audio_done = next(c for c in done_frame["payload"]["contents"] if c["type"] == "file/audio")
    text = audio_done["data"].get("transcription_text")
    assert isinstance(text, str) and text.strip() != ""
    assert "Тестовая транскрипция" in text


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_transcribe_audio_via_ws_command_succeeds(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """WS-команда `sync/messages/transcribe_audio_requested` → reply succeeded → push done."""
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="trws",
            channel_name="trws_ch",
        )
    message_id, _ = await _upload_voice_and_send(sync_auth_token, channel_id)

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        request_id = uuid.uuid4().hex
        await ws_owner.send(json.dumps({
            "request_id": request_id,
            "type": "sync/messages/transcribe_audio_requested",
            "payload": {"channel_id": channel_id, "message_id": message_id},
        }))

        reply = await wait_frame(
            ws_owner,
            type_="sync/messages/transcribe_audio_succeeded",
            where=lambda p: True,
            timeout=15.0,
        )
        assert reply.get("request_id") == request_id

        done = await wait_frame(
            ws_owner,
            type_="sync/message/updated",
            where=lambda p: p.get("id") == message_id and any(
                c["type"] == "file/audio" and c.get("data", {}).get("transcription_status") == "done"
                for c in p.get("contents", [])
            ),
            timeout=60.0,
        )

    audio_done = next(c for c in done["payload"]["contents"] if c["type"] == "file/audio")
    text = audio_done["data"].get("transcription_text")
    assert isinstance(text, str) and text.strip() != ""
