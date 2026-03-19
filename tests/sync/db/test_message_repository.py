"""Тесты MessageRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel, SyncMessage, SyncThread
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.models.messages import MessageContentModel, MessageContentType, TextPlainContent


@pytest.mark.asyncio
async def test_message_create_and_list(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    """Создание сообщений с контентом и выборка по каналу."""
    ch = SyncChannel(
        channel_id="ch_msg",
        company_id=company_id,
        type="topic",
        name="general",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch)

    contents = [
        MessageContentModel(
            type=MessageContentType.TEXT_PLAIN,
            data=TextPlainContent(body="hello world"),
            order=0,
        ),
    ]

    msg = await message_repo.create_message(
        message_id="msg_1",
        company_id=company_id,
        channel_id="ch_msg",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="user_1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=contents,
    )
    assert msg.message_id == "msg_1"

    listed = await message_repo.list_by_channel("ch_msg", company_id=company_id)
    assert len(listed) == 1
    assert listed[0].message_id == "msg_1"

    content_rows = await message_repo.list_contents("msg_1")
    assert len(content_rows) == 1
    assert content_rows[0].type == "text/plain"
    assert content_rows[0].data["body"] == "hello world"


@pytest.mark.asyncio
async def test_message_list_by_thread(
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    """Выборка сообщений по треду."""
    ch = SyncChannel(
        channel_id="ch_thr",
        company_id=company_id,
        type="topic",
        name="test",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch)

    thread = SyncThread(
        thread_id="thr_1",
        company_id=company_id,
        channel_id="ch_thr",
        root_message_id="msg_root",
        title="Test Thread",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await thread_repo.create(thread)

    await message_repo.create_message(
        message_id="msg_root",
        company_id=company_id,
        channel_id="ch_thr",
        thread_id="thr_1",
        parent_message_id=None,
        sender_user_id="user_1",
        status="sent",
        sent_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="root"), order=0),
        ],
    )

    await message_repo.create_message(
        message_id="msg_reply",
        company_id=company_id,
        channel_id="ch_thr",
        thread_id="thr_1",
        parent_message_id="msg_root",
        sender_user_id="user_2",
        status="sent",
        sent_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="reply"), order=0),
        ],
    )

    thread_msgs = await message_repo.list_by_thread("thr_1", company_id=company_id)
    assert [m.message_id for m in thread_msgs] == ["msg_root", "msg_reply"]
