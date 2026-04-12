"""Канал: флаг transcribe_voice_messages и авто-STT для file/audio."""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any

import pytest
from httpx import AsyncClient

from tests.fixtures.audio_bytes import minimal_wav_silence


async def _create_topic_channel(client: AsyncClient, headers: dict[str, str]) -> str:
    pr = await client.post(
        "/sync/api/v1/spaces/",
        headers=headers,
        json={"name": "VoiceFlagSpace", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    cr = await client.post(
        "/sync/api/v1/channels/",
        headers=headers,
        json={
            "space_id": space_id,
            "type": "topic",
            "name": "voice_flag_ch",
            "is_private": False,
        },
    )
    assert cr.status_code == 201
    return cr.json()["id"]


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
async def test_voice_message_without_channel_flag_stays_idle(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers)
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
@pytest.mark.timeout(20)
async def test_voice_message_with_channel_flag_processing_then_done_via_worker(
    sync_service,
    sync_worker,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=120.0) as client:
        channel_id = await _create_topic_channel(client, sync_auth_headers)
        patch = await client.patch(
            f"/sync/api/v1/channels/{channel_id}",
            headers=sync_auth_headers,
            json={"transcribe_voice_messages": True},
        )
        assert patch.status_code == 200
        wav = minimal_wav_silence(duration_sec=0.05)
        up = await client.post(
            "/sync/api/v1/files/",
            headers=sync_auth_headers,
            files={"file": ("note.wav", io.BytesIO(wav), "audio/wav")},
        )
        assert up.status_code == 200
        f = up.json()
        sr = await client.post(
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
            lr = await client.get(
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
