"""Дополнительные сценарии MessageRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.channel import SyncChannel
from apps.sync.models.message import SyncMessage, SyncMessageContent
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    ReactionEntry,
    TextPlainContent,
)


@pytest.mark.asyncio
async def test_get_by_id_for_company(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    ch_g = f"{unique_id}_ch_g"
    m_gc = f"{unique_id}_m_gc"
    other_co = f"{unique_id}_other_co"
    ch = SyncChannel(
        channel_id=ch_g,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    _ = await SyncMessage.create_with_contents(
        message_id=m_gc,
        company_id=company_id,
        channel_id=ch_g,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=datetime.now(tz=UTC),
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="x"), order=0),
        ],
    )
    row = await SyncMessage.find_in_company(company_id, m_gc)
    assert row is not None
    assert row.message_id == m_gc
    assert await SyncMessage.find_in_company(other_co, m_gc) is None
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await SyncMessage.find_in_company("", m_gc)
    with pytest.raises(ValueError, match="message_id cannot be empty"):
        _ = await SyncMessage.find_in_company(company_id, "")


@pytest.mark.asyncio
async def test_replace_contents_soft_delete_reactions_max_sent(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    ch_r = f"{unique_id}_ch_r"
    m_r = f"{unique_id}_m_r"
    ch = SyncChannel(
        channel_id=ch_r,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    _ = await SyncMessage.create_with_contents(
        message_id=m_r,
        company_id=company_id,
        channel_id=ch_r,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=t0,
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="a"), order=0),
        ],
    )
    mx = await SyncMessage.max_root_lane_sent_at(ch_r, company_id=company_id)
    assert mx == t0

    ed = datetime(2026, 1, 2, 10, 0, 0, tzinfo=UTC)
    await SyncMessage.replace_contents(
        m_r,
        [
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="b"), order=0),
        ],
        ed,
    )
    contents = await SyncMessageContent.list_for_message(m_r)
    assert len(contents) == 1
    assert isinstance(contents[0].data, TextPlainContent)
    assert contents[0].data.body == "b"

    await SyncMessage.set_reactions(
        m_r,
        [ReactionEntry(user_id="u1", emoji="x", created_at=ed)],
    )
    m2 = await SyncMessage.find_in_company(company_id, m_r)
    assert m2 is not None
    assert len(m2.reactions) == 1

    await SyncMessage.soft_delete(m_r, datetime.now(tz=UTC))
    m3 = await SyncMessage.find_in_company(company_id, m_r)
    assert m3 is not None
    assert m3.deleted_at is not None


@pytest.mark.asyncio
async def test_get_thread_root_chain(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    ch_trt = f"{unique_id}_ch_trt"
    root = f"{unique_id}_root"
    c1 = f"{unique_id}_c1"
    c2 = f"{unique_id}_c2"
    ch = SyncChannel(
        channel_id=ch_trt,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    t = datetime.now(tz=UTC)
    _ = await SyncMessage.create_with_contents(
        message_id=root,
        company_id=company_id,
        channel_id=ch_trt,
        thread_id=None,
        parent_message_id=None,
        sender_user_id="u1",
        status="sent",
        sent_at=t,
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="r"), order=0),
        ],
    )
    _ = await SyncMessage.create_with_contents(
        message_id=c1,
        company_id=company_id,
        channel_id=ch_trt,
        thread_id=None,
        parent_message_id=root,
        sender_user_id="u2",
        status="sent",
        sent_at=t,
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="c1"), order=0),
        ],
    )
    _ = await SyncMessage.create_with_contents(
        message_id=c2,
        company_id=company_id,
        channel_id=ch_trt,
        thread_id=None,
        parent_message_id=c1,
        sender_user_id="u2",
        status="sent",
        sent_at=t,
        contents=[
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="c2"), order=0),
        ],
    )
    root_msg = await SyncMessage.thread_root(c2)
    assert root_msg is not None
    assert root_msg.message_id == root


@pytest.mark.asyncio
async def test_list_by_channel_pagination(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    ch_pg = f"{unique_id}_ch_pg"
    ch = SyncChannel(
        channel_id=ch_pg,
        company_id=company_id,
        namespace="default",
        type="topic",
        name="t",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    for i in range(5):
        mid = f"{unique_id}_pg_{i}"
        _ = await SyncMessage.create_with_contents(
            message_id=mid,
            company_id=company_id,
            channel_id=ch_pg,
            thread_id=None,
            parent_message_id=None,
            sender_user_id="u1",
            status="sent",
            sent_at=datetime(2026, 1, 1, i, 0, 0, tzinfo=UTC),
            contents=[
                MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body=str(i)), order=0),
            ],
        )
    rows = await SyncMessage.list_root_lane(ch_pg, limit=2, offset=0, company_id=company_id)
    assert len(rows) == 2
