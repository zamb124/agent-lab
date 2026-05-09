"""Канал: флаг transcribe_voice_messages и авто-STT для file/audio."""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any

import pytest

from tests.fixtures.audio_bytes import minimal_wav_silence
from tests.sync.api._helpers import create_topic_channel_via_http


async def _create_topic_channel(
    client: AsyncClient, headers: dict[str, str], company_id: str, unique_id: str
) -> str:
    return await create_topic_channel_via_http(
        client,
        headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="voice",
        channel_name="voice_flag_ch",
    )


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


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_voice_message_without_channel_flag_stays_idle(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers, company_id, unique_id)
    wav = minimal_wav_silence(duration_sec=0.05)
    up = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("note.wav", io.BytesIO(wav), "audio/wav")},
    )
    assert up.status_code == 200
    f = up.json()
    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [_audio_content_block(f)],
        },
    )
    assert sr.status_code == 201
    msg = sr.json()
    audio = next(c for c in msg["contents"] if c["type"] == "file/audio")
    assert audio["data"]["transcription_status"] == "idle"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_voice_message_with_channel_flag_processing_then_done_via_worker(
    sync_client,
    sync_worker,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers, company_id, unique_id)
    patch = await sync_client.patch(
        f"/sync/api/v1/channels/{channel_id}",
        headers=sync_auth_headers,
        json={"transcribe_voice_messages": True},
    )
    assert patch.status_code == 200
    wav = minimal_wav_silence(duration_sec=0.05)
    up = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("note.wav", io.BytesIO(wav), "audio/wav")},
    )
    assert up.status_code == 200
    f = up.json()
    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [_audio_content_block(f)],
        },
    )
    assert sr.status_code == 201
    msg = sr.json()
    message_id = msg["id"]
    audio = next(c for c in msg["contents"] if c["type"] == "file/audio")
    assert audio["data"]["transcription_status"] == "processing"

    deadline = time.monotonic() + 90.0
    done_text: str | None = None
    while time.monotonic() < deadline:
        lr = await sync_client.get(
            f"/sync/api/v1/channels/{channel_id}/messages",
            headers=sync_auth_headers,
        )
        assert lr.status_code == 200
        for m in lr.json()["items"]:
            if m["id"] != message_id:
                continue
            for c in m["contents"]:
                if c["type"] != "file/audio":
                    continue
                st = c["data"].get("transcription_status")
                if st == "done":
                    done_text = c["data"].get("transcription_text")
                    break
            if done_text is not None:
                break
        if done_text is not None:
            break
        await asyncio.sleep(0.4)

    assert done_text is not None
    assert done_text.strip() != ""
    assert "Тестовая транскрипция" in done_text
