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
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    mp4 = _minimal_mp4_bytes()
    from tests.sync.api._helpers import seed_namespace_via_repo

    namespace = f"ns_{unique_id}_vid"
    await seed_namespace_via_repo(company_id, namespace)
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=120.0) as client:
        cr = await client.post(
            "/sync/api/v1/channels/",
            headers=sync_auth_headers,
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "video_tx_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201
        channel_id = cr.json()["id"]

        up = await client.post(
            "/sync/api/v1/files/",
            headers=sync_auth_headers,
            files={"file": ("clip.mp4", io.BytesIO(mp4), "video/mp4")},
        )
        assert up.status_code == 200
        f = up.json()
        sr = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            headers=sync_auth_headers,
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
            headers=sync_auth_headers,
        )
        assert tx.status_code == 200
        v0 = next(c for c in tx.json()["contents"] if c["type"] == "file/video")
        assert v0["data"]["transcription_status"] == "processing"

        deadline = time.monotonic() + 120.0
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
@pytest.mark.timeout(60)
async def test_transcribe_call_aggregate_includes_guest_line(
    sync_service,
    sync_worker,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    from datetime import UTC, datetime

    from apps.sync.container import get_sync_container
    from apps.sync.db.models import SyncCallParticipant
    from apps.sync.realtime.operations import MessagesSendPayload, op_messages_send
    from apps.sync.models.messages import (
        AudioAttachmentContent,
        MessageContentModel,
        MessageContentType,
        MessageCreate,
    )
    from core.models.identity_models import User

    guest_label = "ГостьАгрегат"

    from tests.sync.api._helpers import seed_namespace_via_repo

    namespace = f"ns_{unique_id}_callagg"
    await seed_namespace_via_repo(company_id, namespace)
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=120.0) as client:
        cr = await client.post(
            "/sync/api/v1/channels/",
            headers=sync_auth_headers,
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "call_agg_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201
        channel_id = cr.json()["id"]
        patch = await client.patch(
            f"/sync/api/v1/channels/{channel_id}",
            headers=sync_auth_headers,
            json={"transcribe_voice_messages": True},
        )
        assert patch.status_code == 200

        link_r = await client.post(
            "/sync/api/v1/calls/links",
            headers=sync_auth_headers,
            json={"channel_id": channel_id, "call_type": "video", "ttl_hours": 1},
        )
        assert link_r.status_code == 201
        token = link_r.json()["link_token"]

        join_reg = await client.post(
            f"/sync/api/v1/calls/join/{token}",
            headers=sync_auth_headers,
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
            headers=sync_auth_headers,
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
            headers=sync_auth_headers,
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
        guest_user = User(user_id=guest_id, name=guest_id, active_company_id=company_id)
        from core.context import Context, clear_context, set_context
        from core.models.i18n_models import Language
        from core.models.identity_models import Company

        set_context(
            Context(
                user=guest_user,
                active_company=Company(
                    company_id=company_id,
                    name=f"Sync test {company_id}",
                    owner_user_id=guest_user.user_id,
                ),
                user_companies=[],
                channel="test",
                language=Language.RU,
            )
        )
        try:
            guest_message = await op_messages_send(
                MessagesSendPayload(channel_id=channel_id, body=body_guest),
                user=guest_user,
                container=container,
            )
        finally:
            clear_context()
        guest_message_id = guest_message.id

        deadline = time.monotonic() + 90.0
        guest_done = False
        while time.monotonic() < deadline:
            lr = await client.get(
                f"/sync/api/v1/channels/{channel_id}/messages",
                headers=sync_auth_headers,
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
            headers=sync_auth_headers,
        )
        assert agg.status_code == 202

        deadline2 = time.monotonic() + 90.0
        found_entries: list[dict] | None = None
        while time.monotonic() < deadline2:
            lr = await client.get(
                f"/sync/api/v1/channels/{channel_id}/messages",
                headers=sync_auth_headers,
            )
            assert lr.status_code == 200
            for m in lr.json()["items"]:
                for c in m.get("contents") or []:
                    if c.get("type") == "call/transcript" and isinstance(c.get("data"), dict):
                        entries = c["data"].get("entries", [])
                        has_guest = any(
                            e.get("display_name") == guest_label and e.get("is_guest") is True
                            for e in entries
                        )
                        has_transcription = any(
                            "Тестовая транскрипция" in (e.get("text") or "")
                            for e in entries
                        )
                        if has_guest and has_transcription:
                            found_entries = entries
                            break
                if found_entries is not None:
                    break
            if found_entries is not None:
                break
            await asyncio.sleep(0.5)

        assert found_entries is not None
        guest_entry = next(e for e in found_entries if e.get("is_guest") is True)
        assert guest_entry["display_name"] == guest_label
        assert "Тестовая транскрипция" in guest_entry["text"]
