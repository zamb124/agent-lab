"""HTTP тесты API встреч Sync."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.sync.db.models import (
    SyncCall,
    SyncCallMeeting,
    SyncCallRecording,
    SyncChannel,
    SyncFile,
    SyncSpace,
)


@pytest.mark.asyncio
async def test_meetings_list_and_get(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    system_user_id: str,
    space_repo,
    channel_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    file_repo,
) -> None:
    company_id = "system"
    user_id = system_user_id
    space = SyncSpace(
        space_id=uuid4().hex,
        company_id=company_id,
        name="S",
        description=None,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id=uuid4().hex,
        company_id=company_id,
        space_id=space.space_id,
        type="topic",
        name="general",
        is_private=False,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
        pinned_message_ids=[],
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, user_id, "owner", company_id=company_id)
    call = SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"call-{uuid4().hex[:8]}",
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await call_repo.create_call(call)
    raw_file = SyncFile(
        file_id=uuid4().hex,
        company_id=company_id,
        original_name="meeting.mp4",
        mime_type="video/mp4",
        size_bytes=1024,
        storage_url="https://files.example/list/raw.mp4",
        checksum=None,
    )
    await file_repo.create(raw_file)
    transcript_file = SyncFile(
        file_id=uuid4().hex,
        company_id=company_id,
        original_name="meeting.txt",
        mime_type="text/plain",
        size_bytes=64,
        storage_url="https://files.example/list/transcript.txt",
        checksum=None,
    )
    await file_repo.create(transcript_file)
    recording = SyncCallRecording(
        recording_id=uuid4().hex,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        status="uploaded",
        raw_file_id=raw_file.file_id,
        created_at=datetime.now(UTC),
    )
    await call_recording_repo.create(recording)
    meeting = SyncCallMeeting(
        meeting_id=uuid4().hex,
        call_id=call.call_id,
        recording_id=recording.recording_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        transcript_text_file_id=transcript_file.file_id,
        summary_json={"short_summary": "ok"},
        export_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await call_meeting_repo.create(meeting)

    list_resp = await sync_client.get("/sync/api/v1/meetings/", headers=auth_headers_system)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert any(item["meeting_id"] == meeting.meeting_id for item in payload)
    listed = next(item for item in payload if item["meeting_id"] == meeting.meeting_id)
    assert listed["transcript_text_storage_url"] == "https://files.example/list/transcript.txt"
    assert listed["transcript_text_download_url"] == (
        f"/sync/api/v1/meetings/{meeting.meeting_id}/download/transcript"
    )

    details_resp = await sync_client.get(
        f"/sync/api/v1/meetings/{meeting.meeting_id}",
        headers=auth_headers_system,
    )
    assert details_resp.status_code == 200
    details = details_resp.json()
    assert details["meeting"]["meeting_id"] == meeting.meeting_id
    assert details["recording"]["raw_file_storage_url"] == "https://files.example/list/raw.mp4"
    assert details["recording"]["raw_file_download_url"] == (
        f"/sync/api/v1/meetings/{meeting.meeting_id}/download/raw"
    )
    assert details["meeting"]["transcript_text_storage_url"] == "https://files.example/list/transcript.txt"
    assert details["meeting"]["transcript_text_download_url"] == (
        f"/sync/api/v1/meetings/{meeting.meeting_id}/download/transcript"
    )


@pytest.mark.asyncio
async def test_retry_processing_uses_mock_stt_client_and_updates_transcript(
    sync_client,
    auth_headers_system,
    monkeypatch,
    sync_db_clean: None,
    system_user_id: str,
    space_repo,
    channel_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    file_repo,
    mock_sync_recording_source,
    mock_sync_stt_client,
) -> None:
    from apps.sync.api import meetings as meetings_api
    from apps.sync.realtime import tasks as sync_tasks

    company_id = "system"
    user_id = system_user_id
    space = SyncSpace(
        space_id=uuid4().hex,
        company_id=company_id,
        name="Retry Space",
        description=None,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id=uuid4().hex,
        company_id=company_id,
        space_id=space.space_id,
        type="topic",
        name="retry",
        is_private=False,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
        pinned_message_ids=[],
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, user_id, "owner", company_id=company_id)
    call = SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"call-{uuid4().hex[:8]}",
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await call_repo.create_call(call)
    raw_file = SyncFile(
        file_id=uuid4().hex,
        company_id=company_id,
        original_name="meeting.mp4",
        mime_type="video/mp4",
        size_bytes=1024,
        storage_url="http://recordings.local/retry/raw.mp4",
        checksum=None,
    )
    await file_repo.create(raw_file)
    recording = SyncCallRecording(
        recording_id=uuid4().hex,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        status="uploaded",
        raw_file_id=raw_file.file_id,
        provider_job_id="egress-retry",
        created_at=datetime.now(UTC),
    )
    await call_recording_repo.create(recording)
    meeting = SyncCallMeeting(
        meeting_id=uuid4().hex,
        call_id=call.call_id,
        recording_id=recording.recording_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        summary_json={},
        export_status="failed",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await call_meeting_repo.create(meeting)

    mock_sync_recording_source(b"RIFF_retry_audio", "audio/wav")
    stt_client = mock_sync_stt_client("Тестовый retry transcript")

    async def _no_summary_kiq(**kwargs):
        return None

    async def _run_transcribe_kiq(**kwargs):
        await sync_tasks.sync_transcribe_recording_task(**kwargs)

    monkeypatch.setattr(sync_tasks.sync_summarize_transcript_task, "kiq", _no_summary_kiq)
    monkeypatch.setattr(meetings_api.sync_transcribe_recording_task, "kiq", _run_transcribe_kiq)

    retry_resp = await sync_client.post(
        f"/sync/api/v1/meetings/{meeting.meeting_id}/retry-processing",
        headers=auth_headers_system,
    )
    assert retry_resp.status_code == 200
    retry_payload = retry_resp.json()
    assert retry_payload["meeting_id"] == meeting.meeting_id
    assert retry_payload["export_status"] == "pending"
    assert isinstance(retry_payload["transcript_text_file_id"], str)
    assert retry_payload["transcript_text_file_id"] != ""
    assert retry_payload["transcript_text_storage_url"] is None
    assert retry_payload["transcript_text_download_url"] == (
        f"/sync/api/v1/meetings/{meeting.meeting_id}/download/transcript"
    )
    assert len(stt_client.calls) >= 1


@pytest.mark.asyncio
async def test_sync_files_download_proxies_syncfile_storage_url(
    sync_client,
    auth_headers_system,
    monkeypatch,
    sync_db_clean: None,
    file_repo,
) -> None:
    import core.http as core_http

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.content = b"proxied-file-content"
            self.headers = {"content-type": "video/mp4"}

        def raise_for_status(self) -> None:
            return None

    class _FakeClientContext:
        async def __aenter__(self) -> "_FakeClientContext":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str):
            assert url == "http://recordings.local/files/file.mp4"
            return _FakeResponse()

    def _fake_get_httpx_client(*, timeout: float, **kwargs):
        return _FakeClientContext()

    monkeypatch.setattr(core_http, "get_httpx_client", _fake_get_httpx_client)

    sync_file = SyncFile(
        file_id=uuid4().hex,
        company_id="system",
        original_name="file.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        storage_url="http://recordings.local/files/file.mp4",
        checksum=None,
    )
    await file_repo.create(sync_file)

    response = await sync_client.get(
        f"/sync/api/v1/files/download/{sync_file.file_id}",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    assert response.content == b"proxied-file-content"
    assert response.headers["content-type"].startswith("video/mp4")


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_meeting_transcript_and_manual_export(
    all_services,
    sync_worker,
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    system_user_id: str,
    space_repo,
    channel_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    file_repo,
    wait_for_meeting_pipeline_complete,
) -> None:
    company_id = "system"
    user_id = system_user_id

    space = SyncSpace(
        space_id=uuid4().hex,
        company_id=company_id,
        name="Space Manual Export",
        description=None,
        namespace=None,
        auto_export_transcript_to_crm=False,
        auto_export_summary_to_crm=False,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id=uuid4().hex,
        company_id=company_id,
        space_id=space.space_id,
        type="topic",
        name="calls",
        is_private=False,
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
        pinned_message_ids=[],
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, user_id, "owner", company_id=company_id)
    call = SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"call-{uuid4().hex[:8]}",
        created_at=datetime.now(UTC),
        created_by_user_id=user_id,
    )
    await call_repo.create_call(call)
    raw_file = SyncFile(
        file_id=uuid4().hex,
        company_id=company_id,
        original_name="meeting.mp4",
        mime_type="video/mp4",
        size_bytes=128,
        storage_url="sync://meetings/manual/raw.mp4",
        checksum=None,
    )
    await file_repo.create(raw_file)
    recording = SyncCallRecording(
        recording_id=uuid4().hex,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        status="uploaded",
        raw_file_id=raw_file.file_id,
        provider_job_id="egress-test",
        created_at=datetime.now(UTC),
    )
    await call_recording_repo.create(recording)
    transcript_file = SyncFile(
        file_id=f"{recording.recording_id}-transcript",
        company_id=company_id,
        original_name="meeting.txt",
        mime_type="text/plain",
        size_bytes=17,
        storage_url="sync://meetings/manual/transcript.txt",
        checksum=None,
    )
    await file_repo.create(transcript_file)
    meeting = SyncCallMeeting(
        meeting_id=uuid4().hex,
        call_id=call.call_id,
        recording_id=recording.recording_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        transcript_file_id=transcript_file.file_id,
        transcript_text_file_id=transcript_file.file_id,
        summary_json={"short_summary": "Короткое summary встречи"},
        export_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await call_meeting_repo.create(meeting)

    transcript_resp = await sync_client.get(
        f"/sync/api/v1/meetings/{meeting.meeting_id}/transcript",
        headers=auth_headers_system,
    )
    assert transcript_resp.status_code == 200
    transcript_payload = transcript_resp.json()
    assert transcript_payload["file_id"] == transcript_file.file_id
    assert transcript_payload["storage_url"] == "sync://meetings/manual/transcript.txt"

    export_resp = await sync_client.post(
        f"/sync/api/v1/meetings/{meeting.meeting_id}/export/crm",
        headers=auth_headers_system,
        json={"namespace": "support.manual"},
    )
    assert export_resp.status_code == 200
    export_payload = export_resp.json()
    assert export_payload["meeting_id"] == meeting.meeting_id
    assert export_payload["export_target_namespace"] == "support.manual"

    updated = await wait_for_meeting_pipeline_complete(
        meeting_id=meeting.meeting_id,
        company_id=company_id,
        timeout_seconds=30.0,
        expected_namespace="support.manual",
        require_export_done=True,
    )
    assert updated.export_status == "done"
