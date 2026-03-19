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

    assert await channel_repo.is_member("ch_mbr", "user_10") is False

    await channel_repo.upsert_member("ch_mbr", "user_10", "member", company_id)
    assert await channel_repo.is_member("ch_mbr", "user_10") is True

    await channel_repo.add_member_if_missing("ch_mbr", "user_10", "admin", company_id)
    assert await channel_repo.is_member("ch_mbr", "user_10") is True
