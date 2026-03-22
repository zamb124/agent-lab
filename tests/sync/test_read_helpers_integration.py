"""Интеграционные тесты channel_read_helpers и message_read_helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.channel_lane_preview import ChannelLaneSummary
from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.db.models import SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.common import UserBrief
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageRead,
    TextPlainContent,
)
from core.models.identity_models import User


@pytest.mark.asyncio
async def test_channel_read_direct_peer_without_user_repo(
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_dir",
        company_id=company_id,
        space_id=None,
        type="direct",
        name=None,
        is_private=True,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_dir", "alice", "member", company_id=company_id)
    await channel_repo.upsert_member("ch_dir", "bob", "member", company_id=company_id)

    read = await channel_read_from_entity(
        ch,
        viewer_user_id="alice",
        channel_repository=channel_repo,
        user_repository=None,
        company_id=company_id,
    )
    assert read.peer is not None
    assert read.peer.id == "bob"
    assert read.peer.display_name == "bob"


@pytest.mark.asyncio
async def test_channel_read_direct_peer_with_user_repository(
    channel_repo: ChannelRepository,
    sync_user_repository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    peer_id = f"sync_peer_{company_id}"
    await sync_user_repository.set(
        User(
            user_id=peer_id,
            name="Peer Display Name",
            emails=[f"{peer_id}@test.local"],
            companies={company_id: ["member"]},
            active_company_id=company_id,
        )
    )
    ch = SyncChannel(
        channel_id="ch_dir2",
        company_id=company_id,
        space_id=None,
        type="direct",
        name=None,
        is_private=True,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="viewer_x",
    )
    await channel_repo.create(ch)
    await channel_repo.upsert_member("ch_dir2", "viewer_x", "member", company_id=company_id)
    await channel_repo.upsert_member("ch_dir2", peer_id, "member", company_id=company_id)

    read = await channel_read_from_entity(
        ch,
        viewer_user_id="viewer_x",
        channel_repository=channel_repo,
        user_repository=sync_user_repository,
        company_id=company_id,
    )
    assert read.peer is not None
    assert read.peer.id == peer_id
    assert read.peer.display_name == "Peer Display Name"


@pytest.mark.asyncio
async def test_channel_read_topic_no_peer_lane_summary(
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    ch = SyncChannel(
        channel_id="ch_top",
        company_id=company_id,
        space_id=None,
        type="topic",
        name="General",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    await channel_repo.create(ch)
    summ = ChannelLaneSummary(
        unread_count=3,
        last_message_preview="hi",
        last_message_at=datetime.now(tz=UTC),
    )
    read = await channel_read_from_entity(
        ch,
        viewer_user_id="u1",
        channel_repository=channel_repo,
        user_repository=None,
        company_id=company_id,
        lane_summary=summ,
    )
    assert read.peer is None
    assert read.unread_count == 3
    assert read.last_message_preview == "hi"


def test_message_read_from_entity_builds_read() -> None:
    from apps.sync.db.models import SyncMessage

    m = SyncMessage(
        message_id="m1",
        company_id="c1",
        channel_id="ch1",
        thread_id=None,
        parent_message_id=None,
        sender_user_id="sender1",
        status="sent",
        sent_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        reactions=[{"user_id": "u1", "emoji": "ok", "created_at": "2026-01-01T12:00:00+00:00"}],
    )
    contents = [
        MessageContentModel(
            type=MessageContentType.TEXT_PLAIN,
            data=TextPlainContent(body="hello"),
            order=0,
        ),
    ]
    sender = UserBrief(id="sender1", display_name="Sender", avatar_url=None)
    out: MessageRead = message_read_from_entity(m=m, contents=contents, sender=sender)
    assert out.id == "m1"
    assert out.sender.display_name == "Sender"
    assert len(out.contents) == 1
    assert len(out.reactions) == 1
    assert out.reactions[0].emoji == "ok"
