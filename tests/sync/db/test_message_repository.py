"""Тесты MessageRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel, SyncThread
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
    unique_id: str,
) -> None:
    """Создание сообщений с контентом и выборка по каналу."""
    _ = sync_db_clean
    ch_msg = f"{unique_id}_ch_msg"
    msg_1 = f"{unique_id}_msg_1"
    ch = SyncChannel(
        channel_id=ch_msg,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="general",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    _ = await channel_repo.create(ch)

    contents = [
        MessageContentModel(
            type=MessageContentType.TEXT_PLAIN,
            data=TextPlainContent(body="hello world"),
            order=0,
        ),
    ]

    msg = await message_repo.create_message(
        message_id=msg_1,
        company_id=company_id,
        channel_id=ch_msg,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="user_1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=contents,
    )
    assert msg.message_id == msg_1

    listed = await message_repo.list_by_channel(ch_msg, company_id=company_id)
    assert len(listed) == 1
    assert listed[0].message_id == msg_1

    listed_contents = await message_repo.list_contents(msg_1)
    assert len(listed_contents) == 1
    assert listed_contents[0].type == MessageContentType.TEXT_PLAIN
    assert isinstance(listed_contents[0].data, TextPlainContent)
    assert listed_contents[0].data.body == "hello world"


@pytest.mark.asyncio
async def test_message_list_by_thread(
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Выборка сообщений по треду."""
    _ = sync_db_clean
    ch_thr = f"{unique_id}_ch_thr"
    thr_1 = f"{unique_id}_thr_1"
    msg_root = f"{unique_id}_msg_root"
    msg_reply = f"{unique_id}_msg_reply"
    ch = SyncChannel(
        channel_id=ch_thr,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="test",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    _ = await channel_repo.create(ch)

    thread = SyncThread(
        thread_id=thr_1,
        company_id=company_id,
        channel_id=ch_thr,
        root_message_id=msg_root,
        title="Test Thread",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    _ = await thread_repo.create(thread)

    _ = await message_repo.create_message(
        message_id=msg_root,
        company_id=company_id,
        channel_id=ch_thr,
        thread_id=thr_1,
        parent_message_id=None,
        sender_user_id="user_1",
        status="sent",
        sent_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="root"), order=0),
        ],
    )

    _ = await message_repo.create_message(
        message_id=msg_reply,
        company_id=company_id,
        channel_id=ch_thr,
        thread_id=thr_1,
        parent_message_id=msg_root,
        sender_user_id="user_2",
        status="sent",
        sent_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="reply"), order=0),
        ],
    )

    thread_msgs = await message_repo.list_by_thread(thr_1, company_id=company_id)
    assert [m.message_id for m in thread_msgs] == [msg_root, msg_reply]


@pytest.mark.asyncio
async def test_main_channel_feed_includes_reply_with_parent(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Основная лента канала (thread_id IS NULL) включает ответы с parent_message_id."""
    _ = sync_db_clean
    ch_main = f"{unique_id}_ch_main"
    root_a = f"{unique_id}_root_a"
    reply_b = f"{unique_id}_reply_b"
    ch = SyncChannel(
        channel_id=ch_main,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="main",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    _ = await channel_repo.create(ch)

    _ = await message_repo.create_message(
        message_id=root_a,
        company_id=company_id,
        channel_id=ch_main,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="user_1",
        status="sent",
        sent_at=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="root"), order=0),
        ],
    )
    _ = await message_repo.create_message(
        message_id=reply_b,
        company_id=company_id,
        channel_id=ch_main,
        thread_id=None,
        parent_message_id=root_a,
        sender_user_id="user_2",
        status="sent",
        sent_at=datetime(2026, 1, 2, 10, 1, tzinfo=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="reply"), order=0),
        ],
    )

    listed = await message_repo.list_by_channel(ch_main, company_id=company_id, limit=50)
    ids = {m.message_id for m in listed}
    assert ids == {root_a, reply_b}


@pytest.mark.asyncio
async def test_channel_lane_summaries_batch_unread_and_preview(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Сводка ленты: непрочитанные чужие сообщения и превью последнего."""
    _ = sync_db_clean
    ch_lane = f"{unique_id}_ch_lane"
    m1 = f"{unique_id}_m1"
    ch = SyncChannel(
        channel_id=ch_lane,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="lane",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u_viewer",
    )
    _ = await channel_repo.create(ch)
    await channel_repo.upsert_member(ch_lane, "u_viewer", "owner", company_id=company_id)

    t_msg = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    _ = await message_repo.create_message(
        message_id=m1,
        company_id=company_id,
        channel_id=ch_lane,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u_other",
        status="sent",
        sent_at=t_msg,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="hello lane"),
                order=0,
            ),
        ],
    )

    batch = await message_repo.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=[ch_lane],
        viewer_user_id="u_viewer",
    )
    summ = batch[ch_lane]
    assert summ.unread_count == 1
    assert summ.mention_unread_count == 0
    assert summ.last_message_preview == "hello lane"
    assert summ.last_message_at is not None

    await channel_repo.set_member_last_read_at(
        ch_lane,
        "u_viewer",
        datetime(2026, 3, 1, 13, 0, 0, tzinfo=UTC),
        company_id=company_id,
    )
    batch2 = await message_repo.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=[ch_lane],
        viewer_user_id="u_viewer",
    )
    assert batch2[ch_lane].unread_count == 0
    assert batch2[ch_lane].mention_unread_count == 0


@pytest.mark.asyncio
async def test_channel_lane_summaries_batch_mention_unread_count(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    ch_men = f"{unique_id}_ch_men"
    m_men = f"{unique_id}_m_men"
    ch = SyncChannel(
        channel_id=ch_men,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="mentions",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u_viewer",
    )
    _ = await channel_repo.create(ch)
    await channel_repo.upsert_member(ch_men, "u_viewer", "owner", company_id=company_id)
    await channel_repo.upsert_member(ch_men, "u_other", "member", company_id=company_id)
    t_msg = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
    _ = await message_repo.create_message(
        message_id=m_men,
        company_id=company_id,
        channel_id=ch_men,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u_other",
        status="sent",
        sent_at=t_msg,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="hi you", mentions=["u_viewer"]),
                order=0,
            ),
        ],
    )
    batch = await message_repo.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=[ch_men],
        viewer_user_id="u_viewer",
    )
    assert batch[ch_men].unread_count == 1
    assert batch[ch_men].mention_unread_count == 1
