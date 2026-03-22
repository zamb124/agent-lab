"""Негативные ветки execute_command (handlers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel, SyncSpace
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.git import GitProvider, GitResourceKind, GitResourceRefCreate
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    TextPlainContent,
)
from apps.sync.models.threads import ThreadCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command


def _cmd(*, actor: str, company_id: str, typ: str, payload: dict) -> CommandEnvelope:
    return CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=actor,
        company_id=company_id,
        type=typ,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_channels_create_direct_wrong_member_count(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    body = ChannelCreate(
        space_id=None,
        type=ChannelType.DIRECT,
        name=None,
        is_private=True,
        member_ids=[],
    )
    with pytest.raises(ValueError, match="ровно один"):
        await execute_command(
            _cmd(actor="u1", company_id=company_id, typ="channels.create", payload={"body": body.model_dump()}),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_create_direct_self(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    body = ChannelCreate(
        space_id=None,
        type=ChannelType.DIRECT,
        name=None,
        is_private=True,
        member_ids=["u1"],
    )
    with pytest.raises(ValueError, match="самим собой"):
        await execute_command(
            _cmd(actor="u1", company_id=company_id, typ="channels.create", payload={"body": body.model_dump()}),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_create_topic_missing_space(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    body = ChannelCreate(
        space_id=None,
        type=ChannelType.TOPIC,
        name="n",
        is_private=False,
    )
    with pytest.raises(ValueError, match="space_id"):
        await execute_command(
            _cmd(actor="u1", company_id=company_id, typ="channels.create", payload={"body": body.model_dump()}),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_create_topic_missing_name(
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
        space_id="sp_nm",
        company_id=company_id,
        name="S",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await space_repo.create(sp)
    body = ChannelCreate(
        space_id="sp_nm",
        type=ChannelType.TOPIC,
        name=None,
        is_private=False,
    )
    with pytest.raises(ValueError, match="name"):
        await execute_command(
            _cmd(actor="u1", company_id=company_id, typ="channels.create", payload={"body": body.model_dump()}),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_channels_update_empty_body(
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
        channel_id="ch_empty_u",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_empty_u", "u1", "owner", company_id=company_id)
    with pytest.raises(ValueError, match="Нет полей"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="channels.update",
                payload={"channel_id": "ch_empty_u", "body": {}},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_edit_not_author(
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
        channel_id="ch_ed",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u_other",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_ed", "u_other", "owner", company_id=company_id)
    await channel_repo.upsert_member("ch_ed", "u1", "member", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_ed",
        company_id=company_id,
        channel_id="ch_ed",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u_other",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    edit_body = MessageEdit(
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="y"),
                order=0,
            ),
        ],
    )
    with pytest.raises(ValueError, match="только автор"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.edit",
                payload={
                    "channel_id": "ch_ed",
                    "message_id": "msg_ed",
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


@pytest.mark.asyncio
async def test_messages_delete_other_as_member(
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
        channel_id="ch_del",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u_other",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_del", "u_other", "owner", company_id=company_id)
    await channel_repo.upsert_member("ch_del", "u1", "member", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_del",
        company_id=company_id,
        channel_id="ch_del",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u_other",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    with pytest.raises(ValueError, match="Недостаточно прав"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.delete",
                payload={"channel_id": "ch_del", "message_id": "msg_del"},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_forward_deleted(
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
        channel_id="ch_f",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_f", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_f",
        company_id=company_id,
        channel_id="ch_f",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    await message_repo.soft_delete_message("msg_f", datetime.now(tz=UTC))
    with pytest.raises(ValueError, match="удалённое"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.forward",
                payload={
                    "from_channel_id": "ch_f",
                    "to_channel_id": "ch_f",
                    "message_id": "msg_f",
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


@pytest.mark.asyncio
async def test_messages_react_deleted(
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
        channel_id="ch_rx",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_rx", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_rx",
        company_id=company_id,
        channel_id="ch_rx",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    await message_repo.soft_delete_message("msg_rx", datetime.now(tz=UTC))
    with pytest.raises(ValueError, match="удалено"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.react",
                payload={"channel_id": "ch_rx", "message_id": "msg_rx", "emoji": "ok"},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_pin_not_owner(
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
        channel_id="ch_pin",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u_other",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_pin", "u_other", "owner", company_id=company_id)
    await channel_repo.upsert_member("ch_pin", "u1", "member", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_pin",
        company_id=company_id,
        channel_id="ch_pin",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u_other",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    with pytest.raises(ValueError, match="владелец"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.pin",
                payload={"channel_id": "ch_pin", "message_id": "msg_pin", "action": "add"},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_pin_deleted(
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
        channel_id="ch_pd",
        company_id=company_id,
        space_id=None,
        type=ChannelType.GROUP.value,
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_pd", "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_pd",
        company_id=company_id,
        channel_id="ch_pd",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    await message_repo.soft_delete_message("msg_pd", datetime.now(tz=UTC))
    with pytest.raises(ValueError, match="удалённое"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.pin",
                payload={"channel_id": "ch_pd", "message_id": "msg_pd", "action": "add"},
            ),
            spaces=space_repo,
            channels=channel_repo,
            threads=thread_repo,
            messages=message_repo,
            git_refs=git_ref_repo,
            user_repository=sync_user_repository,
        )


@pytest.mark.asyncio
async def test_messages_edit_channel_mismatch(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    for cid in ("ch_m1", "ch_m2"):
        ch = SyncChannel(
            channel_id=cid,
            company_id=company_id,
            space_id=None,
            type=ChannelType.GROUP.value,
            name="a",
            is_private=False,
            created_at=datetime.now(tz=UTC),
            created_by_user_id="u1",
        )
        await channel_repo.create(ch)
        await channel_repo.upsert_member(cid, "u1", "owner", company_id=company_id)
    await message_repo.create_message(
        message_id="msg_mm",
        company_id=company_id,
        channel_id="ch_m1",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="x"),
                order=0,
            ),
        ],
    )
    edit_body = MessageEdit(
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="y"),
                order=0,
            ),
        ],
    )
    with pytest.raises(ValueError, match="Несовпадение канала"):
        await execute_command(
            _cmd(
                actor="u1",
                company_id=company_id,
                typ="messages.edit",
                payload={
                    "channel_id": "ch_m2",
                    "message_id": "msg_mm",
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


@pytest.mark.asyncio
async def test_threads_create_missing_root(
    space_repo,
    channel_repo,
    thread_repo,
    message_repo,
    git_ref_repo,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    tc = ThreadCreate(root_message_id="no_such_root", title=None)
    with pytest.raises(ValueError, match="не найден"):
        await execute_command(
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


@pytest.mark.asyncio
async def test_git_resources_upsert_idempotent(
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
        project_key="pk",
        external_id="ext1",
        url="https://gitlab.example/x",
        extra={"a": 1},
    )
    r1 = await execute_command(
        _cmd(actor="u1", company_id=company_id, typ="git.resources.upsert", payload={"body": gc.model_dump()}),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r1.ok and r1.result is not None
    gc2 = GitResourceRefCreate(
        provider=GitProvider.GITLAB,
        kind=GitResourceKind.REPO,
        project_key="pk",
        external_id="ext1",
        url="https://gitlab.example/y",
        extra={"b": 2},
    )
    r2 = await execute_command(
        _cmd(actor="u1", company_id=company_id, typ="git.resources.upsert", payload={"body": gc2.model_dump()}),
        spaces=space_repo,
        channels=channel_repo,
        threads=thread_repo,
        messages=message_repo,
        git_refs=git_ref_repo,
        user_repository=sync_user_repository,
    )
    assert r2.ok and r2.result is not None
    assert r2.result.url == "https://gitlab.example/y"
