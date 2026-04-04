"""REST: transcribe-video и transcribe-call с реальным sync_worker и HTTP Sync (9005)."""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.fixtures.audio_bytes import minimal_wav_silence


def _minimal_mp4_bytes() -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("Для transcribe-video нужен ffmpeg в PATH")
    out_path = Path(tempfile.gettempdir()) / f"sync_stt_vid_{uuid.uuid4().hex[:10]}.mp4"
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.5",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:d=0.5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(out_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            pytest.skip(
                "ffmpeg не смог собрать тестовый mp4: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(20)
async def test_transcribe_video_endpoint_marks_done_via_worker(
    sync_service,
    sync_worker,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    mp4 = _minimal_mp4_bytes()
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=120.0) as client:
        pr = await client.post(
            "/sync/api/v1/spaces/",
            headers=auth_headers_system,
            json={"name": "VideoTxSpace", "description": None},
        )
        assert pr.status_code == 201
        space_id = pr.json()["id"]
        cr = await client.post(
            "/sync/api/v1/channels/",
            headers=auth_headers_system,
            json={
                "space_id": space_id,
                "type": "topic",
                "name": "video_tx_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201
        channel_id = cr.json()["id"]

        up = await client.post(
            "/sync/api/v1/files/",
            headers=auth_headers_system,
            files={"file": ("clip.mp4", io.BytesIO(mp4), "video/mp4")},
        )
        assert up.status_code == 200
        f = up.json()
        sr = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            headers=auth_headers_system,
            json={
                "thread_id": None,
                "parent_message_id": None,
                "contents": [
                    {
                        "type": "file/video",
                        "order": 0,
                        "data": {
                            "file_id": f["file_id"],
                            "filename": "clip.mp4",
                            "mime_type": "video/mp4",
                            "size": f["file_size"],
                        },
                    },
                ],
            },
        )
        assert sr.status_code == 201
        message_id = sr.json()["id"]

        tx = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/transcribe-video",
            headers=auth_headers_system,
        )
        assert tx.status_code == 200
        v0 = next(c for c in tx.json()["contents"] if c["type"] == "file/video")
        assert v0["data"]["transcription_status"] == "processing"

        deadline = time.monotonic() + 120.0
        done_text: str | None = None
        while time.monotonic() < deadline:
            lr = await client.get(
                f"/sync/api/v1/channels/{channel_id}/messages",
                headers=auth_headers_system,
            )
            assert lr.status_code == 200
            for m in lr.json()["items"]:
                if m["id"] != message_id:
                    continue
                for c in m["contents"]:
                    if c["type"] != "file/video":
                        continue
                    if c["data"].get("transcription_status") == "done":
                        done_text = c["data"].get("transcription_text")
                        break
                if done_text is not None:
                    break
            if done_text is not None:
                break
            await asyncio.sleep(0.5)

        assert done_text is not None
        assert "Тестовая транскрипция" in done_text


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(20)
async def test_transcribe_call_aggregate_includes_guest_line(
    sync_service,
    sync_worker,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    from datetime import UTC, datetime

    from apps.sync.container import get_sync_container
    from apps.sync.db.models import SyncCallParticipant
    from apps.sync.realtime.commands import CommandEnvelope
    from apps.sync.realtime.handlers import execute_command
    from apps.sync.models.messages import (
        AudioAttachmentContent,
        MessageContentModel,
        MessageContentType,
        MessageCreate,
    )

    company_id = "system"
    guest_label = "ГостьАгрегат"

    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=120.0) as client:
        pr = await client.post(
            "/sync/api/v1/spaces/",
            headers=auth_headers_system,
            json={"name": "CallAggSpace", "description": None},
        )
        assert pr.status_code == 201
        space_id = pr.json()["id"]
        cr = await client.post(
            "/sync/api/v1/channels/",
            headers=auth_headers_system,
            json={
                "space_id": space_id,
                "type": "topic",
                "name": "call_agg_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201
        channel_id = cr.json()["id"]
        patch = await client.patch(
            f"/sync/api/v1/channels/{channel_id}",
            headers=auth_headers_system,
            json={"transcribe_voice_messages": True},
        )
        assert patch.status_code == 200

        link_r = await client.post(
            "/sync/api/v1/calls/links",
            headers=auth_headers_system,
            json={"channel_id": channel_id, "call_type": "video", "ttl_hours": 1},
        )
        assert link_r.status_code == 201
        token = link_r.json()["link_token"]

        join_reg = await client.post(
            f"/sync/api/v1/calls/join/{token}",
            headers=auth_headers_system,
        )
        assert join_reg.status_code == 200
        call_id = join_reg.json()["call_id"]

        join_guest = await client.post(
            f"/sync/api/v1/calls/join/{token}",
            json={"guest_name": guest_label},
        )
        assert join_guest.status_code == 200
        guest_id = join_guest.json()["identity"]
        assert guest_id.startswith("guest:")
        owner_identity = join_reg.json()["identity"]

        container = get_sync_container()
        for uid in (owner_identity, guest_id):
            await container.call_repository.add_participant(
                SyncCallParticipant(
                    id=uuid.uuid4().hex,
                    call_id=call_id,
                    user_id=uid,
                    status="joined",
                    joined_at=datetime.now(UTC),
                )
            )

        tr = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            headers=auth_headers_system,
            json={
                "thread_id": None,
                "parent_message_id": None,
                "call_id": call_id,
                "contents": [
                    {
                        "type": "text/plain",
                        "order": 0,
                        "data": {"body": "реплика владельца перед гостем"},
                    },
                ],
            },
        )
        assert tr.status_code == 201

        wav = minimal_wav_silence(duration_sec=0.05)
        up = await client.post(
            "/sync/api/v1/files/",
            headers=auth_headers_system,
            files={"file": ("g.wav", io.BytesIO(wav), "audio/wav")},
        )
        assert up.status_code == 200
        f = up.json()

        body_guest = MessageCreate(
            thread_id=None,
            parent_message_id=None,
            contents=[
                MessageContentModel(
                    type=MessageContentType.FILE_AUDIO,
                    data=AudioAttachmentContent(
                        file_id=f["file_id"],
                        filename="g.wav",
                        mime_type="audio/wav",
                        size=f["file_size"],
                        duration_ms=500,
                    ),
                    order=0,
                ),
            ],
            mentioned_user_ids=None,
            call_id=call_id,
        )
        cmd_guest = CommandEnvelope(
            id=uuid.uuid4().hex,
            actor_user_id=guest_id,
            company_id=company_id,
            type="messages.send",
            payload={"channel_id": channel_id, "body": body_guest.model_dump(mode="json")},
        )
        res_guest = await execute_command(
            cmd_guest,
            spaces=container.space_repository,
            channels=container.channel_repository,
            threads=container.thread_repository,
            messages=container.message_repository,
            git_refs=container.git_resource_ref_repository,
            user_repository=container.user_repository,
            calls=container.call_repository,
        )
        assert res_guest.ok
        guest_message_id = res_guest.result.id

        deadline = time.monotonic() + 90.0
        guest_done = False
        while time.monotonic() < deadline:
            lr = await client.get(
                f"/sync/api/v1/channels/{channel_id}/messages",
                headers=auth_headers_system,
            )
            assert lr.status_code == 200
            for m in lr.json()["items"]:
                if m["id"] != guest_message_id:
                    continue
                for c in m["contents"]:
                    if c["type"] == "file/audio" and c["data"].get("transcription_status") == "done":
                        guest_done = True
                        break
            if guest_done:
                break
            await asyncio.sleep(0.4)
        assert guest_done

        agg = await client.post(
            f"/sync/api/v1/channels/{channel_id}/calls/{call_id}/transcribe",
            headers=auth_headers_system,
        )
        assert agg.status_code == 202

        deadline2 = time.monotonic() + 90.0
        found_body: str | None = None
        while time.monotonic() < deadline2:
            lr = await client.get(
                f"/sync/api/v1/channels/{channel_id}/messages",
                headers=auth_headers_system,
            )
            assert lr.status_code == 200
            for m in lr.json()["items"]:
                parts: list[str] = []
                for c in m.get("contents") or []:
                    if c.get("type") == "text/plain" and isinstance(c.get("data"), dict):
                        b = c["data"].get("body")
                        if isinstance(b, str) and b.strip() != "":
                            parts.append(b.strip())
                joined = "\n".join(parts)
                if guest_label in joined and "Тестовая транскрипция" in joined:
                    found_body = joined
                    break
            if found_body is not None:
                break
            await asyncio.sleep(0.5)

        assert found_body is not None
        assert f"[{guest_label}]" in found_body
