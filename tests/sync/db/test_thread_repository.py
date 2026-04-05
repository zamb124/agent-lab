"""Тесты ThreadRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel, SyncThread
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.models.messages import MessageContentModel, MessageContentType, TextPlainContent


@pytest.mark.asyncio
async def test_thread_list_by_channel_order(
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """list_by_channel возвращает треды по убыванию created_at."""
    channel_id = f"ch_tr_{unique_id}"
    ch = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)

    t_old = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_new = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    root_old = f"root_old_{unique_id}"
    root_new = f"root_new_{unique_id}"
    thr_old = f"thr_old_{unique_id}"
    thr_new = f"thr_new_{unique_id}"

    await message_repo.create_message(
        message_id=root_old,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=t_old,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="a"),
                order=0,
            ),
        ],
    )
    await message_repo.create_message(
        message_id=root_new,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=t_new,
        contents=[
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body="b"),
                order=0,
            ),
        ],
    )

    thread_old = SyncThread(
        thread_id=thr_old,
        company_id=company_id,
        channel_id=channel_id,
        root_message_id=root_old,
        title=None,
        created_at=t_old,
        created_by_user_id="u1",
    )
    thread_new = SyncThread(
        thread_id=thr_new,
        company_id=company_id,
        channel_id=channel_id,
        root_message_id=root_new,
        title=None,
        created_at=t_new,
        created_by_user_id="u1",
    )
    await thread_repo.create(thread_old)
    await thread_repo.create(thread_new)

    rows = await thread_repo.list_by_channel(channel_id, company_id=company_id)
    assert [r.thread_id for r in rows] == [thr_new, thr_old]


@pytest.mark.asyncio
async def test_thread_list_empty_channel(
    channel_repo: ChannelRepository,
    thread_repo: ThreadRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    empty_id = f"ch_empty_{unique_id}"
    ch = SyncChannel(
        channel_id=empty_id,
        company_id=company_id,
        type="topic",
        name="e",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    rows = await thread_repo.list_by_channel(empty_id, company_id=company_id)
    assert rows == []
