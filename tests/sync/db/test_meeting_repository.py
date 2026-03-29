"""Интеграционные тесты репозиториев встреч и записей."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.sync.db.models import SyncCall, SyncCallMeeting, SyncCallRecording, SyncChannel, SyncSpace
from apps.sync.db.repositories.meeting_repository import CallMeetingRepository, CallRecordingRepository


@pytest.mark.asyncio
async def test_create_and_list_recordings(
    call_recording_repo: CallRecordingRepository,
    call_meeting_repo: CallMeetingRepository,
    call_repo,
    channel_repo,
    space_repo,
    sync_db_clean: None,
    company_id: str,
) -> None:
    space = SyncSpace(
        space_id=uuid4().hex,
        company_id=company_id,
        name="Space",
        description=None,
        created_at=datetime.now(UTC),
        created_by_user_id="u1",
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
        created_by_user_id="u1",
        pinned_message_ids=[],
    )
    await channel_repo.create(channel)
    call = SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"call-{uuid4().hex[:8]}",
        created_by_user_id="u1",
        created_at=datetime.now(UTC),
    )
    await call_repo.create_call(call)

    recording = SyncCallRecording(
        recording_id=uuid4().hex,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        status="recording",
        created_at=datetime.now(UTC),
    )
    await call_recording_repo.create(recording)
    rows = await call_recording_repo.list_for_call(call.call_id, company_id)
    assert len(rows) == 1
    assert rows[0].recording_id == recording.recording_id

    meeting = SyncCallMeeting(
        meeting_id=uuid4().hex,
        call_id=call.call_id,
        recording_id=recording.recording_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        summary_json={},
        export_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await call_meeting_repo.create(meeting)
    meetings = await call_meeting_repo.list_meetings(
        company_id=company_id,
        channel_id=channel.channel_id,
        space_id=space.space_id,
        limit=10,
    )
    assert len(meetings) == 1
    assert meetings[0].meeting_id == meeting.meeting_id
