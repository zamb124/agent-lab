"""Трек egress «речь в ленту»: запись и чтение."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.call import SyncCall
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channels import ChannelType
from apps.sync.models.speech_egress import SyncCallSpeechEgressTrack


@pytest.mark.asyncio
async def test_speech_egress_crud_and_list(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    actor = f"u_{unique_id}"
    channel = SyncChannel(
        channel_id=f"ch_{unique_id}",
        company_id=company_id,
        namespace=f"ns_{unique_id}_egress",
        type=ChannelType.TOPIC.value,
        name="c",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
        speech_to_chat_enabled=True,
    )
    _ = await SyncChannel.objects.create(instance=channel)
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
    _ = await SyncCall.objects.create(instance=call)

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
    assert await SyncCallSpeechEgressTrack.set(row)

    got = await SyncCallSpeechEgressTrack.get_for_track(call.call_id, row.track_sid)
    assert got is not None
    assert got.row_id == row.row_id

    by_eg = await SyncCallSpeechEgressTrack.objects.filter(
        egress_id=row.egress_id
    ).get_or_none()
    assert by_eg is not None
    assert by_eg.track_sid == row.track_sid

    listed = await SyncCallSpeechEgressTrack.list_for_call(call.call_id, company_id)
    assert len(listed) == 1

    await SyncCallSpeechEgressTrack.mark_speech_egress_segments(row.row_id, 2, None)
    fresh = await SyncCallSpeechEgressTrack.get_for_track(call.call_id, row.track_sid)
    assert fresh is not None
    assert fresh.segments_posted == 2
    assert fresh.last_segment_s3_key is None

    await SyncCallSpeechEgressTrack.mark_speech_egress_segments(
        row.row_id,
        3,
        "sync-speech/c/call/u/TR/k1.aac",
    )
    fresh2 = await SyncCallSpeechEgressTrack.get_for_track(call.call_id, row.track_sid)
    assert fresh2 is not None
    assert fresh2.segments_posted == 3
    assert fresh2.last_segment_s3_key == "sync-speech/c/call/u/TR/k1.aac"

    await SyncCallSpeechEgressTrack.delete_for_call(call.call_id, company_id)
    assert await SyncCallSpeechEgressTrack.get_for_track(
        call.call_id, row.track_sid
    ) is None
