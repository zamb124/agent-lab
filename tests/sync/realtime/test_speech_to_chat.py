"""Speech-to-chat: опрос LiveKit egress, наследование флагов, сообщения в ленту.

Без unittest.mock: реальные репозитории, БД, TaskIQ worker там, где помечено real_taskiq.
Структуры с полем file_results для process_new_files — тестовые DTO, не подмена клиентов.
"""

from __future__ import annotations

import asyncio
import io
import uuid
import wave
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from apps.sync.db.models import SyncCall, SyncCallParticipant, SyncCallSpeechEgressTrack, SyncChannel, SyncSpace
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.call_speech_egress_repository import CallSpeechEgressTrackRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.container import get_sync_container
from apps.sync.models.channels import ChannelType
from apps.sync.models.messages import MessageContentType
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from apps.sync.realtime.speech_to_chat_workflow import (
    SpeechToChatPollOutcome,
    process_new_files_for_egress_row,
    run_speech_to_chat_poll_cycle,
    stop_speech_egresses_for_call_room,
)
from core.files.s3_client import S3ClientFactory
from core.models.identity_models import User


def _cmd(actor: str, company_id: str, typ: str, payload: dict) -> CommandEnvelope:
    return CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=actor,
        company_id=company_id,
        type=typ,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_run_poll_cycle_returns_false_when_channel_speech_disabled(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    actor = "u1"
    sp = SyncSpace(
        space_id=f"sp_sd_{unique_id}",
        company_id=company_id,
        name="S",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
        speech_to_chat_enabled=False,
    )
    await space_repo.create(sp)
    ch = SyncChannel(
        channel_id=f"ch_sd_{unique_id}",
        company_id=company_id,
        space_id=sp.space_id,
        type=ChannelType.TOPIC.value,
        name="c",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
        speech_to_chat_enabled=False,
    )
    await channel_repo.create(ch)
    call = SyncCall(
        call_id=f"call_sd_{unique_id}",
        company_id=company_id,
        channel_id=ch.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"room-{unique_id}",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await call_repo.create_call(call)

    out = await run_speech_to_chat_poll_cycle(call_id=call.call_id, company_id=company_id)
    assert out == SpeechToChatPollOutcome(schedule_next=False)


@pytest.mark.asyncio
async def test_run_poll_cycle_returns_false_when_call_not_active(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    actor = "u1"
    sp = SyncSpace(
        space_id=f"sp_ring_{unique_id}",
        company_id=company_id,
        name="S",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await space_repo.create(sp)
    ch = SyncChannel(
        channel_id=f"ch_ring_{unique_id}",
        company_id=company_id,
        space_id=sp.space_id,
        type=ChannelType.TOPIC.value,
        name="c",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
        speech_to_chat_enabled=True,
    )
    await channel_repo.create(ch)
    call = SyncCall(
        call_id=f"call_ring_{unique_id}",
        company_id=company_id,
        channel_id=ch.channel_id,
        mode="sfu",
        call_type="video",
        status="ringing",
        livekit_room_name=f"room-{unique_id}",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await call_repo.create_call(call)

    out = await run_speech_to_chat_poll_cycle(call_id=call.call_id, company_id=company_id)
    assert out == SpeechToChatPollOutcome(schedule_next=False)


@pytest.mark.asyncio
async def test_run_poll_cycle_returns_false_unknown_call(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    out = await run_speech_to_chat_poll_cycle(
        call_id=f"missing_{unique_id}",
        company_id=company_id,
    )
    assert out == SpeechToChatPollOutcome(schedule_next=False)


@pytest.mark.asyncio
async def test_stop_speech_egresses_no_rows_is_noop(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    await stop_speech_egresses_for_call_room(
        call_id=f"noop_{unique_id}",
        company_id=company_id,
        room_name=f"room-{unique_id}",
    )


@pytest.mark.asyncio
async def test_process_new_files_ingests_segment_via_file_processor_like_upload(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    message_repo: MessageRepository,
    speech_egress_repo: CallSpeechEgressTrackRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    actor = "u1"
    await sync_user_repository.set(
        User(
            user_id=actor,
            name="U1",
            emails=[f"u1-{unique_id}@t.local"],
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
    )
    sp = SyncSpace(
        space_id=f"sp_pf_{unique_id}",
        company_id=company_id,
        name="S",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await space_repo.create(sp)
    ch = SyncChannel(
        channel_id=f"ch_pf_{unique_id}",
        company_id=company_id,
        space_id=sp.space_id,
        type=ChannelType.TOPIC.value,
        name="c",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member(ch.channel_id, actor, "owner", company_id=company_id)

    call = SyncCall(
        call_id=f"call_pf_{unique_id}",
        company_id=company_id,
        channel_id=ch.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"room-{unique_id}",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=actor,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )

    row = SyncCallSpeechEgressTrack(
        row_id=f"row_pf_{unique_id}",
        call_id=call.call_id,
        company_id=company_id,
        channel_id=ch.channel_id,
        participant_identity=actor,
        track_sid=f"TR_{unique_id}",
        egress_id=f"EG_{unique_id}",
        segments_posted=0,
    )
    await speech_egress_repo.create(row)

    _buf = io.BytesIO()
    with wave.open(_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        n = int(8000 * 0.4)
        wf.writeframes(b"\x00\x00" * n)
    wav_bytes = _buf.getvalue()
    s3 = S3ClientFactory.create_client_for_bucket("test-bucket")
    try:
        await s3.upload_bytes(
            data=wav_bytes,
            key="sync-speech-test/seg.wav",
            content_type="audio/wav",
            public=True,
        )
        storage_loc = s3.get_public_url("sync-speech-test/seg.wav")
    finally:
        await s3.close()

    egress_info = SimpleNamespace(
        file_results=[
            SimpleNamespace(location=storage_loc, filename="segment-000.wav", size=len(wav_bytes)),
        ]
    )

    await process_new_files_for_egress_row(row=row, egress_info=egress_info, call_id=call.call_id)

    rows = await message_repo.list_by_channel(ch.channel_id, limit=20, company_id=company_id)
    audio_msgs = [
        m
        for m in rows
        if m.call_id == call.call_id
        and any(
            c.type == MessageContentType.FILE_AUDIO.value
            for c in (await message_repo.list_contents(m.message_id))
        )
    ]
    assert len(audio_msgs) == 1

    container = get_sync_container()
    contents = await message_repo.list_contents(audio_msgs[0].message_id)
    audio = next(c for c in contents if c.type == MessageContentType.FILE_AUDIO.value)
    file_id = audio.data["file_id"]
    fr = await container.file_repository.get(file_id)
    assert fr is not None
    assert fr.s3_key.startswith("files/")
    assert audio.data["duration_ms"] >= 300
    assert isinstance(audio.data["mime_type"], str) and audio.data["mime_type"] != ""


@pytest.mark.asyncio
async def test_spaces_create_and_channel_inherit_speech_flags(
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    git_ref_repo: GitResourceRefRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    cmd_space = _cmd(
        "u1",
        company_id,
        "spaces.create",
        {
            "body": {
                "name": "SpSpeech",
                "description": None,
                "transcribe_voice_messages": True,
                "speech_to_chat_enabled": True,
            }
        },
    )
    sr = await execute_command(
        cmd_space,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert sr.ok
    assert sr.result.transcribe_voice_messages is True
    assert sr.result.speech_to_chat_enabled is True

    cmd_ch = _cmd(
        "u1",
        company_id,
        "channels.create",
        {
            "body": {
                "name": "ChSpeech",
                "type": "topic",
                "space_id": sr.result.id,
                "is_private": False,
                "member_ids": None,
            }
        },
    )
    cr = await execute_command(
        cmd_ch,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert cr.ok
    assert cr.result.transcribe_voice_messages is True
    assert cr.result.speech_to_chat_enabled is True


@pytest.mark.asyncio
async def test_channels_update_speech_to_chat_flag(
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    git_ref_repo: GitResourceRefRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    cmd_space = _cmd(
        "u1",
        company_id,
        "spaces.create",
        {"body": {"name": "SpUp", "description": None}},
    )
    sr = await execute_command(
        cmd_space,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert sr.ok
    cmd_ch = _cmd(
        "u1",
        company_id,
        "channels.create",
        {
            "body": {
                "name": "ChUp",
                "type": "topic",
                "space_id": sr.result.id,
                "is_private": False,
                "member_ids": None,
            }
        },
    )
    cr = await execute_command(
        cmd_ch,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert cr.ok
    assert cr.result.speech_to_chat_enabled is False

    cmd_patch = _cmd(
        "u1",
        company_id,
        "channels.update",
        {
            "channel_id": cr.result.id,
            "body": {"speech_to_chat_enabled": True},
        },
    )
    up = await execute_command(
        cmd_patch,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert up.ok
    assert up.result.speech_to_chat_enabled is True


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(40, func_only=True)
async def test_solo_call_invite_with_speech_flag_eventually_posts_audio_via_livekit(
    flows_service,
    sync_worker,
    livekit_demo_publisher,
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    git_ref_repo: GitResourceRefRepository,
    call_repo: CallRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Соло invite → active → kiq poll; publisher с identity=u1; сегмент egress → file/audio в ленте."""
    actor = "u1"
    await sync_user_repository.set(
        User(
            user_id=actor,
            name="Speech LiveKit",
            emails=[f"u1-{unique_id}@t.local"],
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
    )
    cmd_space = _cmd(
        actor,
        company_id,
        "spaces.create",
        {
            "body": {
                "name": f"SpLk-{unique_id}",
                "description": None,
                "speech_to_chat_enabled": True,
            }
        },
    )
    sr = await execute_command(
        cmd_space,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert sr.ok

    cmd_ch = _cmd(
        actor,
        company_id,
        "channels.create",
        {
            "body": {
                "name": f"ChLk-{unique_id}",
                "type": "topic",
                "space_id": sr.result.id,
                "is_private": False,
                "member_ids": None,
            }
        },
    )
    cr = await execute_command(
        cmd_ch,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert cr.ok
    assert cr.result.speech_to_chat_enabled is True

    invite = _cmd(
        actor,
        company_id,
        "call.invite",
        {"channel_id": cr.result.id, "call_type": "video"},
    )
    inv = await execute_command(
        invite,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert inv.ok
    call_id = inv.result.call_id
    room_name = inv.result.livekit_room_name
    assert isinstance(room_name, str) and room_name != ""

    channel_id = cr.result.id
    try:
        await livekit_demo_publisher(
            room_name=room_name,
            identity=actor,
            settle_seconds=2.0,
        )
        # Poll только БД: цикл speech-to-chat выполняет sync_worker (иначе гонка с воркером и два egress на один трек).
        for _ in range(50):
            rows = await message_repo.list_by_channel(channel_id, limit=50, company_id=company_id)
            for m in rows:
                if m.call_id != call_id:
                    continue
                for c in await message_repo.list_contents(m.message_id):
                    if c.type == MessageContentType.FILE_AUDIO.value:
                        return
            await asyncio.sleep(0.35)
        pytest.fail("За отведённое время не появилось сообщения file/audio для speech-to-chat")
    finally:
        await execute_command(
            _cmd(actor, company_id, "call.hangup", {"call_id": call_id}),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            calls=call_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(20, func_only=True)
async def test_sync_speech_poll_task_chain_runs_via_worker(
    flows_service,
    sync_worker,
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    git_ref_repo: GitResourceRefRepository,
    call_repo: CallRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Очередь: sync_speech_to_chat_poll_task не падает для активного звонка без LiveKit (нет треков)."""
    actor = "u1"
    await sync_user_repository.set(
        User(
            user_id=actor,
            name="Poll Chain",
            emails=[f"pc-{unique_id}@t.local"],
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
    )
    cmd_space = _cmd(
        actor,
        company_id,
        "spaces.create",
        {
            "body": {
                "name": f"SpPc-{unique_id}",
                "description": None,
                "speech_to_chat_enabled": True,
            }
        },
    )
    sr = await execute_command(
        cmd_space,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert sr.ok
    cmd_ch = _cmd(
        actor,
        company_id,
        "channels.create",
        {
            "body": {
                "name": f"ChPc-{unique_id}",
                "type": "topic",
                "space_id": sr.result.id,
                "is_private": False,
                "member_ids": None,
            }
        },
    )
    cr = await execute_command(
        cmd_ch,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert cr.ok

    inv = await execute_command(
        _cmd(actor, company_id, "call.invite", {"channel_id": cr.result.id, "call_type": "video"}),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        user_repository=sync_user_repository,
    )
    assert inv.ok
    call_id = inv.result.call_id

    from apps.sync.realtime.tasks import sync_speech_to_chat_poll_task

    t = await sync_speech_to_chat_poll_task.kiq(call_id=call_id, company_id=company_id)
    res = await t.wait_result(timeout=18.0)
    assert not res.is_err, res.error

