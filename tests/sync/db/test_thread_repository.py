"""Тред Sync: порядок в канале."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.channel import SyncChannel
from apps.sync.models.message import SyncMessage
from apps.sync.models.messages import MessageContentModel, MessageContentType, TextPlainContent
from apps.sync.models.threads import SyncThread


@pytest.mark.asyncio
async def test_thread_list_by_channel_order(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    channel_id = f"ch_tr_{unique_id}"
    ch = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)

    t_old = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_new = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    root_old = f"root_old_{unique_id}"
    root_new = f"root_new_{unique_id}"
    thr_old = f"thr_old_{unique_id}"
    thr_new = f"thr_new_{unique_id}"

    _ = await SyncMessage.create_with_contents(
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
    _ = await SyncMessage.create_with_contents(
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
    _ = await SyncThread.objects.create(instance=thread_old)
    _ = await SyncThread.objects.create(instance=thread_new)

    rows = await SyncThread.list_threads_in_channel(
        company_id,
        channel_id,
        limit=100,
        offset=0,
    )
    assert [r.thread_id for r in rows] == [thr_new, thr_old]


@pytest.mark.asyncio
async def test_thread_list_empty_channel(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    empty_id = f"ch_empty_{unique_id}"
    ch = SyncChannel(
        channel_id=empty_id,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="e",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    rows = await SyncThread.list_threads_in_channel(
        company_id,
        empty_id,
        limit=100,
        offset=0,
    )
    assert rows == []
