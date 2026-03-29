"""Матрица execute_command: реальные репозитории, без моков."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncCall, SyncCallParticipant, SyncChannel, SyncSpace
from apps.sync.models.channels import ChannelCreate, ChannelType, ChannelUpdate
from apps.sync.models.git import GitProvider, GitResourceKind, GitResourceRefCreate
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    TextPlainContent,
)
from apps.sync.models.spaces import SpaceCreate, SpaceUpdate
from apps.sync.models.threads import ThreadCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from apps.sync.realtime.tasks import handle_command


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
async def test_call_recording_start_stop_flow(
    flows_service,
    monkeypatch,
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    sync_user_repository,
    mock_sync_recording_source,
    mock_sync_stt_client,
    wait_for_meeting_pipeline_complete,
    sync_db_clean: None,
    system_user_id: str,
) -> None:
    from apps.sync.realtime import tasks as sync_tasks

    company_id = "system"
    actor_user_id = system_user_id

    async def _run_finalize_kiq(**kwargs):
        await sync_tasks.sync_finalize_recording_task(**kwargs)

    async def _run_transcribe_kiq(**kwargs):
        await sync_tasks.sync_transcribe_recording_task(**kwargs)

    async def _run_summarize_kiq(**kwargs):
        meeting_id = kwargs["meeting_id"]
        await call_meeting_repo.update_summary(
            meeting_id,
            {"short_summary": "Тестовое summary после STT"},
        )

    monkeypatch.setattr(sync_tasks.sync_finalize_recording_task, "kiq", _run_finalize_kiq)
    monkeypatch.setattr(sync_tasks.sync_transcribe_recording_task, "kiq", _run_transcribe_kiq)
    monkeypatch.setattr(sync_tasks.sync_summarize_transcript_task, "kiq", _run_summarize_kiq)
    mock_sync_recording_source(
        b"RIFF_fake_audio",
        "audio/wav",
    )
    stt_client = mock_sync_stt_client(
        f"speaker:user:{actor_user_id}: Курьер опоздал на 20 минут.\n"
        "speaker:guest:guest:anon: Подтверждаю, звонок состоялся поздно.",
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
        require_export_done=False,
    )
    assert completed_meeting.transcript_text_file_id is not None
    assert completed_meeting.summary_json is not None
    assert "short_summary" in completed_meeting.summary_json
    assert len(stt_client.calls) >= 1


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_call_recording_pipeline_via_real_queue_worker(
    flows_service,
    sync_worker,
    space_repo,
    channel_repo,
    call_repo,
    call_recording_repo,
    call_meeting_repo,
    wait_for_meeting_pipeline_complete,
    sync_db_clean: None,
    system_user_id: str,
) -> None:
    """Полный pipeline через настоящий queue worker без monkeypatch .kiq."""
    company_id = "system"
    actor_user_id = system_user_id

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

    start_envelope = _cmd(
        actor=actor_user_id,
        company_id=company_id,
        typ="call.recording.start",
        payload={"call_id": call.call_id},
    )
    start_task = await handle_command.kiq(start_envelope.model_dump(mode="json"))
    start_result = await start_task.wait_result(timeout=30)
    assert not start_result.is_err, f"Queue start task failed: {start_result.error}"
    assert start_result.return_value["ok"] is True

    stop_envelope = _cmd(
        actor=actor_user_id,
        company_id=company_id,
        typ="call.recording.stop",
        payload={"call_id": call.call_id},
    )
    stop_task = await handle_command.kiq(stop_envelope.model_dump(mode="json"))
    stop_result = await stop_task.wait_result(timeout=30)
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
