"""Тесты ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncSpace, SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.space_repository import SpaceRepository


@pytest.mark.asyncio
async def test_channel_crud(
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    """Полный CRUD для каналов + list_by_space."""
    space = SyncSpace(
        space_id="space_ch",
        company_id=company_id,
        name="Space",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await space_repo.create(space)

    ch1 = SyncChannel(
        channel_id="ch_1",
        company_id=company_id,
        space_id="space_ch",
        type="topic",
        name="general",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    ch2 = SyncChannel(
        channel_id="ch_2",
        company_id=company_id,
        space_id="space_ch",
        type="group",
        name="backend",
        is_private=True,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch1)
    await channel_repo.create(ch2)

    got = await channel_repo.get("ch_1")
    assert got is not None
    assert got.name == "general"

    by_space = await channel_repo.list_by_space("space_ch", company_id=company_id)
    assert {c.channel_id for c in by_space} == {"ch_1", "ch_2"}

    deleted = await channel_repo.delete("ch_2")
    assert deleted is True
    assert await channel_repo.get("ch_2") is None


@pytest.mark.asyncio
async def test_channel_members(
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    """Управление участниками канала."""
    space = SyncSpace(
        space_id="space_mbr",
        company_id=company_id,
        name="Space",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await space_repo.create(space)

    ch = SyncChannel(
        channel_id="ch_mbr",
        company_id=company_id,
        space_id="space_mbr",
        type="topic",
        name="test",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch)

    assert await channel_repo.is_member("ch_mbr", "user_10", company_id=company_id) is False

    await channel_repo.upsert_member("ch_mbr", "user_10", "member", company_id)
    assert await channel_repo.is_member("ch_mbr", "user_10", company_id=company_id) is True

    await channel_repo.add_member_if_missing("ch_mbr", "user_10", "admin", company_id)
    assert await channel_repo.is_member("ch_mbr", "user_10", company_id=company_id) is True


@pytest.mark.asyncio
async def test_list_for_user_filters_by_membership(
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    space = SyncSpace(
        space_id="space_u",
        company_id=company_id,
        name="S",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    await space_repo.create(space)

    ch_space = SyncChannel(
        channel_id="ch_space_only",
        company_id=company_id,
        space_id="space_u",
        type="topic",
        name="a",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    ch_direct = SyncChannel(
        channel_id="ch_dm",
        company_id=company_id,
        space_id=None,
        type="direct",
        name=None,
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    ch_other = SyncChannel(
        channel_id="ch_secret",
        company_id=company_id,
        space_id="space_u",
        type="topic",
        name="b",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="bob",
    )
    await channel_repo.create(ch_space)
    await channel_repo.create(ch_direct)
    await channel_repo.create(ch_other)

    await channel_repo.upsert_member("ch_space_only", "alice", "member", company_id)
    await channel_repo.upsert_member("ch_dm", "alice", "owner", company_id)
    await channel_repo.upsert_member("ch_secret", "bob", "member", company_id)

    Alice_channels = await channel_repo.list_for_user(
        "alice", company_id=company_id, space_id=None
    )
    assert {c.channel_id for c in Alice_channels} == {"ch_space_only", "ch_dm"}

    alice_in_space = await channel_repo.list_for_user(
        "alice", company_id=company_id, space_id="space_u"
    )
    assert [c.channel_id for c in alice_in_space] == ["ch_space_only"]

    ids = await channel_repo.list_member_user_ids("ch_dm", company_id=company_id)
    assert "alice" in ids
