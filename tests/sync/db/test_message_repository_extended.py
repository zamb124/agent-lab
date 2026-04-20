"""Дополнительные сценарии MessageRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.models.messages import MessageContentModel, MessageContentType, TextPlainContent


@pytest.mark.asyncio
async def test_get_by_id_for_company(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
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
    await channel_repo.create(ch)
    await message_repo.create_message(
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
    row = await message_repo.get_by_id_for_company(m_gc, company_id)
    assert row is not None
    assert row.message_id == m_gc
    assert await message_repo.get_by_id_for_company(m_gc, other_co) is None


@pytest.mark.asyncio
async def test_replace_contents_soft_delete_reactions_max_sent(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
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
    await channel_repo.create(ch)
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    await message_repo.create_message(
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
    mx = await message_repo.max_root_lane_sent_at(ch_r, company_id=company_id)
    assert mx == t0

    ed = datetime(2026, 1, 2, 10, 0, 0, tzinfo=UTC)
    await message_repo.replace_message_contents(
        m_r,
        [
            MessageContentModel(type=MessageContentType.TEXT_PLAIN, data=TextPlainContent(body="b"), order=0),
        ],
        ed,
    )
    contents = await message_repo.list_contents(m_r)
    assert len(contents) == 1
    assert contents[0].data["body"] == "b"

    await message_repo.set_message_reactions(m_r, [{"user_id": "u1", "emoji": "x", "created_at": ed.isoformat()}])
    m2 = await message_repo.get_by_id_for_company(m_r, company_id)
    assert m2 is not None
    assert len(m2.reactions) == 1

    await message_repo.soft_delete_message(m_r, datetime.now(tz=UTC))
    m3 = await message_repo.get_by_id_for_company(m_r, company_id)
    assert m3 is not None
    assert m3.deleted_at is not None


@pytest.mark.asyncio
async def test_get_thread_root_chain(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
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
    await channel_repo.create(ch)
    t = datetime.now(tz=UTC)
    await message_repo.create_message(
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
    await message_repo.create_message(
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
    await message_repo.create_message(
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
    root_msg = await message_repo.get_thread_root(c2)
    assert root_msg is not None
    assert root_msg.message_id == root


@pytest.mark.asyncio
async def test_list_by_channel_pagination(
    channel_repo: ChannelRepository,
    message_repo: MessageRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
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
    await channel_repo.create(ch)
    for i in range(5):
        mid = f"{unique_id}_pg_{i}"
        await message_repo.create_message(
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
    rows = await message_repo.list_by_channel(ch_pg, limit=2, offset=0, company_id=company_id)
    assert len(rows) == 2
