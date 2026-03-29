"""Матрица execute_command: реальные репозитории, без моков."""

from __future__ import annotations

import asyncio
from collections import deque
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from apps.sync.db.models import SyncCall, SyncCallParticipant, SyncCallRecording, SyncChannel, SyncSpace
from apps.sync.models.channels import ChannelCreate, ChannelType, ChannelUpdate
from apps.sync.models.git import GitProvider, GitResourceKind, GitResourceRefCreate
from apps.sync.models.messages import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    TextPlainContent,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.spaces import SpaceCreate, SpaceUpdate
from apps.sync.models.threads import ThreadCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from apps.sync.realtime.tasks import handle_command
from core.clients.stt_client import STTTranscriptionResult
from core.models.identity_models import User


def _cmd(
    *,
    actor: str,
    company_id: str,
    typ: str,
    payload: dict,
) -> CommandEnvelope:
    return CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=actor,
        company_id=company_id,
        type=typ,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_spaces_create(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="spaces.create",
        payload={"body": {"name": "S1", "description": None}},
    )
    res = await execute_command(
        cmd,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    assert res.result is not None
    assert res.result.name == "S1"


@pytest.mark.asyncio
async def test_spaces_update_empty_body_raises(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    sp = SyncSpace(
        space_id="sp1",
        company_id=company_id,
        name="Old",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await space_repo.create(sp)
    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="spaces.update",
        payload={"space_id": "sp1", "body": {}},
    )
    with pytest.raises(ValueError, match="Нет полей"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_spaces_update_wrong_company(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    sp = SyncSpace(
        space_id="sp2",
        company_id=company_id,
        name="N",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await space_repo.create(sp)
    cmd = _cmd(
        actor="u1",
        company_id=f"{company_id}_other",
        typ="spaces.update",
        payload={"space_id": "sp2", "body": {"name": "X"}},
    )
    with pytest.raises(PermissionError, match="другой компании"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_create_topic(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    sp = SyncSpace(
        space_id="spt",
        company_id=company_id,
        name="S",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await space_repo.create(sp)
    body = ChannelCreate(
        space_id="spt",
        type=ChannelType.TOPIC,
        name="general",
        is_private=False,
    )
    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="channels.create",
        payload={"body": body.model_dump()},
    )
    res = await execute_command(
        cmd,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    assert res.result is not None
    assert res.result.name == "general"


@pytest.mark.asyncio
async def test_channels_update_member_forbidden(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    sp = SyncSpace(
        space_id="spc",
        company_id=company_id,
        name="S",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="owner",
    )
    await space_repo.create(sp)
    ch = SyncChannel(
        channel_id="ch_u",
        company_id=company_id,
        space_id="spc",
        type=ChannelType.TOPIC.value,
        name="n",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="owner",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_u", "owner", "owner", company_id=company_id)
    await channel_repo.upsert_member("ch_u", "member1", "member", company_id=company_id)
    body = ChannelUpdate(name="newname")
    cmd = _cmd(
        actor="member1",
        company_id=company_id,
        typ="channels.update",
        payload={"channel_id": "ch_u", "body": body.model_dump(exclude_unset=True)},
    )
    with pytest.raises(PermissionError, match="owner и admin"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_mark_read_not_member(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_nr",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    cmd = _cmd(
        actor="stranger",
        company_id=company_id,
        typ="channels.mark_read",
        payload={"channel_id": "ch_nr"},
    )
    with pytest.raises(PermissionError, match="не состоит"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_typing_member_ok(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_typ",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_typ", "u1", "owner", company_id=company_id)
    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="channels.typing",
        payload={"channel_id": "ch_typ", "typing": True, "thread_id": None},
    )
    res = await execute_command(
        cmd,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    assert res.result is None
    assert len(res.events) == 1
    assert res.events[0].type == "channel.typing"
    assert res.events[0].payload["channel_id"] == "ch_typ"
    assert res.events[0].payload["typing"] is True
    assert res.events[0].payload["user"]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_channels_typing_not_member(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_typ2",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    cmd = _cmd(
        actor="stranger",
        company_id=company_id,
        typ="channels.typing",
        payload={"channel_id": "ch_typ2", "typing": True},
    )
    with pytest.raises(PermissionError, match="не состоит"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_typing_thread_not_found(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_tthr",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_tthr", "u1", "owner", company_id=company_id)
    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="channels.typing",
        payload={"channel_id": "ch_tthr", "typing": True, "thread_id": "missing_thread"},
    )
    with pytest.raises(ValueError, match="не найден"):
        await execute_command(
            cmd,
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_send_and_mark_read(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_m",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_m", "u1", "owner", company_id=company_id)
    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="hi"),
                order=0,
            ),
        ],
    )
    cmd_send = _cmd(
        actor="u1",
        company_id=company_id,
        typ="messages.send",
        payload={"channel_id": "ch_m", "body": body.model_dump()},
    )
    res = await execute_command(
        cmd_send,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    mid = res.result.id
    cmd_mr = _cmd(
        actor="u1",
        company_id=company_id,
        typ="messages.mark_read",
        payload={"channel_id": "ch_m", "message_id": mid},
    )
    res2 = await execute_command(
        cmd_mr,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res2.ok
    assert res2.events


@pytest.mark.asyncio
async def test_messages_send_saves_mentions_in_content(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_ment",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="Team",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_ment", "u1", "owner", company_id=company_id)
    bob = "00000000-0000-4000-8000-0000000000b2"
    await channel_repo.upsert_member("ch_ment", bob, "member", company_id=company_id)
    text_body = f"hey @{bob} check this"
    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body=text_body),
                order=0,
            ),
        ],
        mentioned_user_ids=[bob],
    )
    res = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.send",
            payload={"channel_id": "ch_ment", "body": body.model_dump()},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    msg_read = res.result
    assert msg_read.mentioned_user_ids == [bob]
    rows = await message_repo.list_contents(msg_read.id)
    assert len(rows) >= 1
    data = rows[0].data
    assert isinstance(data, dict)
    assert data.get("mentions") == [bob]


@pytest.mark.asyncio
async def test_messages_edit_delete_react_pin_forward(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch_a = SyncChannel(
        channel_id="ch_a",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="a",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    ch_b = SyncChannel(
        channel_id="ch_b",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="b",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch_a)
    await channel_repo.create(ch_b)
    await channel_repo.upsert_member("ch_a", "u1", "owner", company_id=company_id)
    await channel_repo.upsert_member("ch_b", "u1", "owner", company_id=company_id)

    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="orig"),
                order=0,
            ),
        ],
    )
    r0 = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.send",
            payload={"channel_id": "ch_a", "body": body.model_dump()},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    mid = r0.result.id

    edit_body = MessageEdit(
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="edited"),
                order=0,
            ),
        ],
    )
    r_edit = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.edit",
            payload={
                "channel_id": "ch_a",
                "message_id": mid,
                "body": edit_body.model_dump(),
            },
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r_edit.ok

    r_del = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.delete",
            payload={"channel_id": "ch_a", "message_id": mid},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r_del.ok

    r_send2 = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.send",
            payload={"channel_id": "ch_a", "body": body.model_dump()},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    mid2 = r_send2.result.id

    r_react = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.react",
            payload={"channel_id": "ch_a", "message_id": mid2, "emoji": "👍"},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r_react.ok

    r_pin = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.pin",
            payload={"channel_id": "ch_a", "message_id": mid2, "action": "add"},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r_pin.ok

    r_fwd = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="messages.forward",
            payload={
                "from_channel_id": "ch_a",
                "to_channel_id": "ch_b",
                "message_id": mid2,
                "thread_id": None,
            },
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r_fwd.ok


@pytest.mark.asyncio
async def test_threads_create(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_t",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_t", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="root_t",
        company_id=company_id,
        channel_id="ch_t",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="root"),
                order=0,
            ),
        ],
    )
    tc = ThreadCreate(root_message_id="root_t", title="T1")
    res = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="threads.create",
            payload={"body": tc.model_dump()},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    assert res.result.root_message_id == "root_t"


@pytest.mark.asyncio
async def test_git_resources_upsert(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    gc = GitResourceRefCreate(
        provider=GitProvider.GITLAB,
        kind=GitResourceKind.REPO,
        project_key="p",
        external_id="99",
        url="https://gitlab.example/p/99",
        extra={"k": "v"},
    )
    res = await execute_command(
        _cmd(
            actor="u1",
            company_id=company_id,
            typ="git.resources.upsert",
            payload={"body": gc.model_dump()},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok
    assert res.result is not None
    assert res.result.external_id == "99"


@pytest.mark.asyncio
async def test_call_hangup_auto_stops_recording_for_recording_owner(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    monkeypatch,
    sync_db_clean: None,
    company_id: str,
) -> None:
    from apps.sync.realtime import handlers as handlers_module

    actor_user_id = "u1"
    other_user_id = "u2"
    space = SyncSpace(
        space_id="sp_hangup_owner",
        company_id=company_id,
        name="Hangup Owner Space",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id="ch_hangup_owner",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="calls",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await channel_repo.create(channel)
    call = SyncCall(
        call_id="call_hangup_owner",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="p2p",
        call_type="video",
        status="active",
        livekit_room_name=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=actor_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=other_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    recording = SyncCallRecording(
        recording_id="rec_hangup_owner",
        call_id=call.call_id,
        company_id=company_id,
        channel_id=call.channel_id,
        space_id=space.space_id,
        status="recording",
        started_by_user_id=actor_user_id,
        provider_job_id="egress-owner",
        started_at=datetime.now(tz=UTC),
    )
    await call_recording_repo.create(recording)

    helper_calls: list[str] = []

    async def _fake_stop_and_finalize_recording(**kwargs):
        helper_calls.append(kwargs["recording"].recording_id)
        return CallRecordingRead(
            recording_id=kwargs["recording"].recording_id,
            call_id=kwargs["call"].call_id,
            channel_id=kwargs["call"].channel_id,
            space_id=kwargs["recording"].space_id,
            status="uploaded",
            provider_job_id=kwargs["recording"].provider_job_id,
            raw_file_id=None,
            started_at=kwargs["recording"].started_at,
            ended_at=datetime.now(tz=UTC),
            created_at=kwargs["recording"].created_at,
            error=None,
        )

    monkeypatch.setattr(handlers_module, "_stop_and_finalize_recording", _fake_stop_and_finalize_recording)

    result = await execute_command(
        _cmd(
            actor=actor_user_id,
            company_id=company_id,
            typ="call.hangup",
            payload={"call_id": call.call_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
        user_repository=sync_user_repository,
    )
    assert result.ok
    assert helper_calls == ["rec_hangup_owner"]
    assert any(event.type == "call.recording.stopped" for event in result.events)


@pytest.mark.asyncio
async def test_call_hangup_does_not_stop_recording_for_non_owner(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    monkeypatch,
    sync_db_clean: None,
    company_id: str,
) -> None:
    from apps.sync.realtime import handlers as handlers_module

    owner_user_id = "u1"
    actor_user_id = "u2"
    space = SyncSpace(
        space_id="sp_hangup_non_owner",
        company_id=company_id,
        name="Hangup Non Owner Space",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id="ch_hangup_non_owner",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="calls",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await channel_repo.create(channel)
    call = SyncCall(
        call_id="call_hangup_non_owner",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="p2p",
        call_type="video",
        status="active",
        livekit_room_name=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=owner_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=actor_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    recording = SyncCallRecording(
        recording_id="rec_hangup_non_owner",
        call_id=call.call_id,
        company_id=company_id,
        channel_id=call.channel_id,
        space_id=space.space_id,
        status="recording",
        started_by_user_id=owner_user_id,
        provider_job_id="egress-non-owner",
        started_at=datetime.now(tz=UTC),
    )
    await call_recording_repo.create(recording)

    helper_calls: list[str] = []

    async def _fake_stop_and_finalize_recording(**kwargs):
        helper_calls.append(kwargs["recording"].recording_id)
        return CallRecordingRead(
            recording_id=kwargs["recording"].recording_id,
            call_id=kwargs["call"].call_id,
            channel_id=kwargs["call"].channel_id,
            space_id=kwargs["recording"].space_id,
            status="uploaded",
            provider_job_id=kwargs["recording"].provider_job_id,
            raw_file_id=None,
            started_at=kwargs["recording"].started_at,
            ended_at=datetime.now(tz=UTC),
            created_at=kwargs["recording"].created_at,
            error=None,
        )

    monkeypatch.setattr(handlers_module, "_stop_and_finalize_recording", _fake_stop_and_finalize_recording)

    result = await execute_command(
        _cmd(
            actor=actor_user_id,
            company_id=company_id,
            typ="call.hangup",
            payload={"call_id": call.call_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
        user_repository=sync_user_repository,
    )
    assert result.ok
    assert helper_calls == []
    assert all(event.type != "call.recording.stopped" for event in result.events)


@pytest.mark.asyncio
async def test_call_recording_start_forbidden_for_non_admin(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    owner_user_id = "owner_recording"
    actor_user_id = "member_recording"
    space = SyncSpace(
        space_id="sp_recording_admin_only",
        company_id=company_id,
        name="Recording Admin Only",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id="ch_recording_admin_only",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="calls",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, owner_user_id, "owner", company_id=company_id)
    await channel_repo.upsert_member(channel.channel_id, actor_user_id, "member", company_id=company_id)
    call = SyncCall(
        call_id="call_recording_admin_only",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name="room-recording-admin-only",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await call_repo.create_call(call)

    with pytest.raises(PermissionError, match="Только админ встречи может включать запись"):
        await execute_command(
            _cmd(
                actor=actor_user_id,
                company_id=company_id,
                typ="call.recording.start",
                payload={"call_id": call.call_id},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            calls=call_repo,
            call_recordings=call_recording_repo,
            call_meetings=call_meeting_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_call_recording_stop_allowed_for_recording_starter_non_admin(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    monkeypatch,
    sync_db_clean: None,
    company_id: str,
) -> None:
    from apps.sync.realtime import handlers as handlers_module

    owner_user_id = "owner_recording_stop"
    actor_user_id = "member_recording_stop"
    space = SyncSpace(
        space_id="sp_recording_stop_starter",
        company_id=company_id,
        name="Recording Stop Starter",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id="ch_recording_stop_starter",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="calls",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, owner_user_id, "owner", company_id=company_id)
    await channel_repo.upsert_member(channel.channel_id, actor_user_id, "member", company_id=company_id)
    call = SyncCall(
        call_id="call_recording_stop_starter",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name="room-recording-stop-starter",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await call_repo.create_call(call)
    recording = SyncCallRecording(
        recording_id="rec_recording_stop_starter",
        call_id=call.call_id,
        company_id=company_id,
        channel_id=call.channel_id,
        space_id=space.space_id,
        status="recording",
        started_by_user_id=actor_user_id,
        provider_job_id="egress-recording-stop-starter",
        started_at=datetime.now(tz=UTC),
    )
    await call_recording_repo.create(recording)

    async def _fake_stop_and_finalize_recording(**kwargs):
        return CallRecordingRead(
            recording_id=kwargs["recording"].recording_id,
            call_id=kwargs["call"].call_id,
            channel_id=kwargs["call"].channel_id,
            space_id=kwargs["recording"].space_id,
            started_by_user_id=kwargs["recording"].started_by_user_id,
            status="uploaded",
            provider_job_id=kwargs["recording"].provider_job_id,
            raw_file_id=None,
            started_at=kwargs["recording"].started_at,
            ended_at=datetime.now(tz=UTC),
            created_at=kwargs["recording"].created_at,
            error=None,
        )

    monkeypatch.setattr(handlers_module, "_stop_and_finalize_recording", _fake_stop_and_finalize_recording)

    result = await execute_command(
        _cmd(
            actor=actor_user_id,
            company_id=company_id,
            typ="call.recording.stop",
            payload={"call_id": call.call_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
        user_repository=sync_user_repository,
    )
    assert result.ok
    assert result.result is not None
    assert result.result.status == "uploaded"
    assert any(event.type == "call.recording.stopped" for event in result.events)


@pytest.mark.asyncio
async def test_call_admin_transfer_updates_call_admin(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    owner_user_id = "owner_transfer"
    target_user_id = "target_transfer"
    space = SyncSpace(
        space_id="sp_transfer_admin",
        company_id=company_id,
        name="Transfer Admin Space",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await space_repo.create(space)
    channel = SyncChannel(
        channel_id="ch_transfer_admin",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="calls",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, owner_user_id, "owner", company_id=company_id)
    await channel_repo.upsert_member(channel.channel_id, target_user_id, "member", company_id=company_id)
    call = SyncCall(
        call_id="call_transfer_admin",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name="room-transfer-admin",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=owner_user_id,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=owner_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=target_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )

    result = await execute_command(
        _cmd(
            actor=owner_user_id,
            company_id=company_id,
            typ="call.admin.transfer",
            payload={"call_id": call.call_id, "target_user_id": target_user_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
        user_repository=sync_user_repository,
    )
    assert result.ok
    assert result.result is not None
    assert result.result.created_by_user_id == target_user_id
    assert any(event.type == "call.admin.changed" for event in result.events)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_call_recording_start_stop_flow(
    flows_service,
    sync_worker,
    livekit_demo_publisher,
    mock_sync_stt_client,
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    wait_for_meeting_pipeline_complete,
    sync_db_clean: None,
    system_user_id: str,
) -> None:
    company_id = "system"
    actor_user_id = system_user_id
    mock_sync_stt_client("Тестовая транскрипция звонка")

    await sync_user_repository.set(
        User(
            user_id=actor_user_id,
            name="Recording Start Stop User",
            emails=[f"{actor_user_id}@system.local"],
            companies={company_id: ["owner", "admin"]},
            active_company_id=company_id,
        )
    )
    sp = SyncSpace(
        space_id="sp_call_rec",
        company_id=company_id,
        name="S",
        description=None,
        namespace=None,
        auto_export_transcript_to_crm=False,
        auto_export_summary_to_crm=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await space_repo.create(sp)
    ch = SyncChannel(
        channel_id="ch_call_rec",
        company_id=company_id,
        space_id=sp.space_id,
        type=ChannelType.TOPIC.value,
        name="support",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member(ch.channel_id, actor_user_id, "owner", company_id=company_id)
    call = SyncCall(
        call_id="call_recording_test",
        company_id=company_id,
        channel_id=ch.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name="room-test",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=actor_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id="guest:anon:Partner",
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )

    await livekit_demo_publisher(room_name=call.livekit_room_name)
    start = await execute_command(
        _cmd(
            actor=actor_user_id,
            company_id=company_id,
            typ="call.recording.start",
            payload={"call_id": call.call_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
    )
    assert start.ok
    assert start.result.status in ("recording", "requested")
    await asyncio.sleep(8.0)

    stop = await execute_command(
        _cmd(
            actor=actor_user_id,
            company_id=company_id,
            typ="call.recording.stop",
            payload={"call_id": call.call_id},
        ),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
        calls=call_repo,
        call_recordings=call_recording_repo,
        call_meetings=call_meeting_repo,
    )
    assert stop.ok
    assert stop.result.status == "uploaded"
    meeting = await call_meeting_repo.get_by_recording(stop.result.recording_id, company_id)
    assert meeting is not None
    completed_meeting = await wait_for_meeting_pipeline_complete(
        meeting_id=meeting.meeting_id,
        company_id=company_id,
        timeout_seconds=120.0,
        require_export_done=False,
    )
    assert completed_meeting.transcript_text_file_id is not None
    assert completed_meeting.summary_json is not None
    assert "short_summary" in completed_meeting.summary_json


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(30)
async def test_call_recording_pipeline_via_real_queue_worker(
    flows_service,
    sync_worker,
    livekit_demo_publisher,
    mock_sync_stt_client,
    space_repo,
    channel_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    wait_for_meeting_pipeline_complete,
    sync_db_clean: None,
    system_user_id: str,
) -> None:
    """Полный pipeline через настоящий queue worker без monkeypatch .kiq."""
    company_id = "system"
    actor_user_id = system_user_id
    mock_sync_stt_client("Тестовая транскрипция очереди")

    await sync_user_repository.set(
        User(
            user_id=actor_user_id,
            name="Queue Pipeline User",
            emails=[f"{actor_user_id}@system.local"],
            companies={company_id: ["owner", "admin"]},
            active_company_id=company_id,
        )
    )

    space = SyncSpace(
        space_id=f"sp_queue_{uuid.uuid4().hex[:8]}",
        company_id=company_id,
        name="Queue Pipeline Space",
        description=None,
        namespace=None,
        auto_export_transcript_to_crm=False,
        auto_export_summary_to_crm=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await space_repo.create(space)

    channel = SyncChannel(
        channel_id=f"ch_queue_{uuid.uuid4().hex[:8]}",
        company_id=company_id,
        space_id=space.space_id,
        type=ChannelType.TOPIC.value,
        name="queue-support",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await channel_repo.create(channel)
    await channel_repo.upsert_member(channel.channel_id, actor_user_id, "owner", company_id=company_id)

    call = SyncCall(
        call_id=f"call_queue_{uuid.uuid4().hex[:8]}",
        company_id=company_id,
        channel_id=channel.channel_id,
        mode="sfu",
        call_type="video",
        status="active",
        livekit_room_name=f"room-queue-{uuid.uuid4().hex[:8]}",
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    await call_repo.create_call(call)
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id=actor_user_id,
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )
    await call_repo.add_participant(
        SyncCallParticipant(
            id=uuid.uuid4().hex,
            call_id=call.call_id,
            user_id="guest:queue:Partner",
            status="joined",
            joined_at=datetime.now(tz=UTC),
        )
    )

    await livekit_demo_publisher(room_name=call.livekit_room_name)
    start_envelope = _cmd(
        actor=actor_user_id,
        company_id=company_id,
        typ="call.recording.start",
        payload={"call_id": call.call_id},
    )
    start_task = await handle_command.kiq(start_envelope.model_dump(mode="json"))
    start_result = await start_task.wait_result(timeout=90)
    assert not start_result.is_err, f"Queue start task failed: {start_result.error}"
    assert start_result.return_value["ok"] is True
    await asyncio.sleep(8.0)

    stop_envelope = _cmd(
        actor=actor_user_id,
        company_id=company_id,
        typ="call.recording.stop",
        payload={"call_id": call.call_id},
    )
    stop_task = await handle_command.kiq(stop_envelope.model_dump(mode="json"))
    stop_result = await stop_task.wait_result(timeout=90)
    assert not stop_result.is_err, f"Queue stop task failed: {stop_result.error}"
    assert stop_result.return_value["ok"] is True
    stop_payload = stop_result.return_value["result"]
    assert stop_payload["status"] == "uploaded"

    meeting = await call_meeting_repo.get_by_recording(stop_payload["recording_id"], company_id)
    assert meeting is not None
    completed_meeting = await wait_for_meeting_pipeline_complete(
        meeting_id=meeting.meeting_id,
        company_id=company_id,
        timeout_seconds=60.0,
        require_export_done=False,
    )
    assert completed_meeting.transcript_text_file_id is not None
    assert "short_summary" in (completed_meeting.summary_json or {})

    recording = await call_recording_repo.get(stop_payload["recording_id"])
    assert recording is not None
    assert recording.raw_file_id is not None


@pytest.mark.asyncio
async def test_download_recording_bytes_404_then_success(monkeypatch) -> None:
    from apps.sync.realtime import tasks as sync_tasks

    class _FakeResponse:
        def __init__(self, status_code: int, content: bytes, content_type: str | None) -> None:
            self.status_code = status_code
            self.content = content
            self.headers: dict[str, str] = {}
            if content_type is not None:
                self.headers["content-type"] = content_type

        def raise_for_status(self) -> None:
            raise RuntimeError(f"Unexpected raise_for_status for status={self.status_code}")

    class _FakeClientContext:
        def __init__(self, responses: deque[_FakeResponse], calls: list[str]) -> None:
            self._responses = responses
            self._calls = calls

        async def __aenter__(self) -> "_FakeClientContext":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str) -> _FakeResponse:
            self._calls.append(url)
            if len(self._responses) == 0:
                raise RuntimeError("Нет подготовленного ответа для fake HTTP клиента.")
            return self._responses.popleft()

    responses: deque[_FakeResponse] = deque(
        [
            _FakeResponse(status_code=404, content=b"", content_type=None),
            _FakeResponse(status_code=200, content=b"audio-bytes", content_type="audio/wav"),
        ]
    )
    requested_urls: list[str] = []
    sleep_calls: list[float] = []

    def _fake_get_httpx_client(*, timeout: float, **kwargs) -> _FakeClientContext:
        return _FakeClientContext(responses=responses, calls=requested_urls)

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(sync_tasks, "get_httpx_client", _fake_get_httpx_client)
    monkeypatch.setattr(sync_tasks.asyncio, "sleep", _fake_sleep)

    payload, content_type = await sync_tasks._download_recording_bytes(
        source_url="http://livekit:7880/egress/room/egress.mp4",
        timeout_seconds=5.0,
    )
    assert payload == b"audio-bytes"
    assert content_type == "audio/wav"
    assert requested_urls == [
        "http://livekit:7880/egress/room/egress.mp4",
        "http://livekit:7880/egress/room/egress.mp4",
    ]
    assert sleep_calls == [3.0]


@pytest.mark.asyncio
async def test_download_recording_bytes_rejects_text_error_payload(monkeypatch) -> None:
    from apps.sync.realtime import tasks as sync_tasks

    class _FakeResponse:
        def __init__(self, status_code: int, content: bytes, content_type: str | None) -> None:
            self.status_code = status_code
            self.content = content
            self.headers: dict[str, str] = {}
            if content_type is not None:
                self.headers["content-type"] = content_type

        def raise_for_status(self) -> None:
            raise RuntimeError(f"Unexpected raise_for_status for status={self.status_code}")

    class _FakeClientContext:
        def __init__(self, response: _FakeResponse) -> None:
            self._response = response

        async def __aenter__(self) -> "_FakeClientContext":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str) -> _FakeResponse:
            return self._response

    def _fake_get_httpx_client(*, timeout: float, **kwargs) -> _FakeClientContext:
        return _FakeClientContext(
            response=_FakeResponse(
                status_code=200,
                content=b"Error opening <_io.BytesIO object>: Format not recognised.",
                content_type="text/plain; charset=utf-8",
            )
        )

    monkeypatch.setattr(sync_tasks, "get_httpx_client", _fake_get_httpx_client)

    with pytest.raises(ValueError, match="неподдерживаемый content-type"):
        await sync_tasks._download_recording_bytes(
            source_url="http://livekit:7880/egress/room/egress.mp4",
            timeout_seconds=5.0,
        )


def test_extract_transcript_from_json_payload_ignores_error_payload() -> None:
    from core.clients.stt_client import _extract_transcript_from_json_payload

    payload = {
        "error": "Error opening <_io.BytesIO object>: Format not recognised.",
        "status": "failed",
    }
    assert _extract_transcript_from_json_payload(payload) is None


@pytest.mark.asyncio
async def test_messages_transcribe_audio_sets_processing_and_emits_event(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
    monkeypatch,
) -> None:
    ch = SyncChannel(
        channel_id="ch_audio_tx",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="audio",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_audio_tx", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_audio_tx",
        company_id=company_id,
        channel_id="ch_audio_tx",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.FILE_AUDIO,
                data=AudioAttachmentContent(
                    file_id="file_audio_1",
                    filename="voice.webm",
                    mime_type="audio/webm",
                    size=100,
                    duration_ms=1200,
                ),
                order=0,
            ),
        ],
    )
    from apps.sync.realtime import tasks as sync_tasks
    queued: list[dict[str, str]] = []

    async def _fake_kiq(**kwargs):
        queued.append(kwargs)

    monkeypatch.setattr(sync_tasks.sync_transcribe_audio_message_task, "kiq", _fake_kiq)

    cmd = _cmd(
        actor="u1",
        company_id=company_id,
        typ="messages.transcribe_audio",
        payload={"channel_id": "ch_audio_tx", "message_id": "msg_audio_tx"},
    )
    res = await execute_command(
        cmd,
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert res.ok is True
    assert res.result is not None
    assert len(res.events) == 1
    assert res.events[0].type == "message.updated"
    updated_audio = next(c for c in res.result.contents if c.type == MessageContentType.FILE_AUDIO)
    assert updated_audio.data.transcription_status == AudioTranscriptionStatus.PROCESSING
    assert updated_audio.data.transcription_text is None
    assert len(queued) == 1
    assert queued[0]["channel_id"] == "ch_audio_tx"
    assert queued[0]["message_id"] == "msg_audio_tx"


@pytest.mark.asyncio
async def test_sync_transcribe_audio_message_task_marks_done(
    channel_repo,
    message_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
    monkeypatch,
) -> None:
    from apps.sync.realtime import tasks as sync_tasks

    ch = SyncChannel(
        channel_id="ch_audio_task",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="audio_task",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_audio_task", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_audio_task",
        company_id=company_id,
        channel_id="ch_audio_task",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.FILE_AUDIO,
                data=AudioAttachmentContent(
                    file_id="file_audio_task",
                    filename="voice.webm",
                    mime_type="audio/webm",
                    size=123,
                    duration_ms=1500,
                ),
                order=0,
            ),
        ],
    )

    settings = SimpleNamespace(
        stt=SimpleNamespace(
            cloud_ru=SimpleNamespace(timeout=3.0, language="ru"),
        ),
        server=SimpleNamespace(
            get_service_url=lambda service=None: "http://sync.test" if service == "sync" else "http://localhost:8000",
        ),
    )

    class _MockSttClient:
        async def transcribe_audio(
            self,
            *,
            audio_bytes: bytes,
            file_name: str,
            mime_type: str,
            language: str | None = None,
        ) -> STTTranscriptionResult:
            assert audio_bytes == b"voice-bytes"
            assert file_name == "voice.webm"
            assert mime_type == "audio/webm"
            assert language == "ru"
            return STTTranscriptionResult(
                provider="mock",
                status=AudioTranscriptionStatus.DONE,
                text="Привет из аудио",
                language="ru",
            )

    class _Resp:
        status_code = 200
        content = b"voice-bytes"

        def raise_for_status(self) -> None:
            return None

    class _HttpCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, headers: dict[str, str]):
            assert url == "http://sync.test/sync/api/v1/files/download/file_audio_task"
            return _Resp()

    published_types: list[str] = []

    async def _fake_publish(events):
        for event in events:
            published_types.append(event.type)

    monkeypatch.setattr(sync_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(sync_tasks, "_build_interservice_auth_headers", lambda **kwargs: {"Authorization": "Bearer x"})
    monkeypatch.setattr(sync_tasks, "get_httpx_client", lambda **kwargs: _HttpCtx())
    monkeypatch.setattr(sync_tasks.STTClientFactory, "create_client", staticmethod(lambda: _MockSttClient()))
    monkeypatch.setattr(sync_tasks, "publish_realtime_events", _fake_publish)

    await sync_tasks.sync_transcribe_audio_message_task(
        channel_id="ch_audio_task",
        message_id="msg_audio_task",
        company_id=company_id,
        actor_user_id="u1",
    )

    rows = await message_repo.list_contents("msg_audio_task")
    content = MessageContentModel.model_validate(
        {"type": rows[0].type, "data": rows[0].data, "order": rows[0].order}
    )
    assert content.type == MessageContentType.FILE_AUDIO
    assert content.data.transcription_status == AudioTranscriptionStatus.DONE
    assert content.data.transcription_text == "Привет из аудио"
    assert published_types == ["message.updated"]
