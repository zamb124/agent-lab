"""Репозиторий sync_call_speech_egress_tracks: реальная БД."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncCall, SyncCallSpeechEgressTrack, SyncChannel, SyncSpace
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.call_speech_egress_repository import CallSpeechEgressTrackRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.models.channels import ChannelType


@pytest.mark.asyncio
async def test_speech_egress_crud_and_list(
    sync_db_clean: None,
    company_id: str,
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    call_repo: CallRepository,
    speech_egress_repo: CallSpeechEgressTrackRepository,
    unique_id: str,
) -> None:
    actor = f"u_{unique_id}"
    space = SyncSpace(
        space_id=f"sp_{unique_id}",
        company_id=company_id,
        name="S",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id=f"ch_{unique_id}",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="c",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
        speech_to_chat_enabled=True,
    )
    await channel_repo.create(channel)
    call = SyncCall(
        call_id=f"call_{unique_id}",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"room-{unique_id}",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await call_repo.create_call(call)

    row = SyncCallSpeechEgressTrack(
        row_id=f"row_{unique_id}",
        call_id=call.call_id,
        company_id=company_id,
        channel_id=channel.channel_id,
        participant_identity=actor,
        track_sid=f"TR_{unique_id}",
        egress_id=f"EG_{unique_id}",
        segments_posted=0,
    )
    created = await speech_egress_repo.create(row)
    assert created.egress_id == row.egress_id

    got = await speech_egress_repo.get_by_call_and_track(call.call_id, row.track_sid)
    assert got is not None
    assert got.row_id == row.row_id

    by_eg = await speech_egress_repo.get_by_egress_id(row.egress_id)
    assert by_eg is not None
    assert by_eg.track_sid == row.track_sid

    listed = await speech_egress_repo.list_for_call(call.call_id, company_id)
    assert len(listed) == 1

    await speech_egress_repo.set_segments_posted(row.row_id, 2)
    fresh = await speech_egress_repo.get_by_call_and_track(call.call_id, row.track_sid)
    assert fresh is not None
    assert fresh.segments_posted == 2
    assert fresh.last_segment_s3_key is None

    await speech_egress_repo.set_segments_posted(
        row.row_id, 3, last_segment_s3_key="sync-speech/c/call/u/TR/k1.aac"
    )
    fresh2 = await speech_egress_repo.get_by_call_and_track(call.call_id, row.track_sid)
    assert fresh2 is not None
    assert fresh2.segments_posted == 3
    assert fresh2.last_segment_s3_key == "sync-speech/c/call/u/TR/k1.aac"

    await speech_egress_repo.delete_for_call(call.call_id, company_id)
    assert await speech_egress_repo.get_by_call_and_track(call.call_id, row.track_sid) is None
