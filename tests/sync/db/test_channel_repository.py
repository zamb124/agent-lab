"""Тесты ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository


@pytest.mark.asyncio
async def test_channel_crud(
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Полный CRUD для каналов + list_by_namespace."""
    namespace = f"ns_{unique_id}_crud"
    ch1 = f"{unique_id}_ch_1"
    ch2 = f"{unique_id}_ch_2"

    ch1_obj = SyncChannel(
        channel_id=ch1,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name="general",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    ch2_obj = SyncChannel(
        channel_id=ch2,
        company_id=company_id,
        namespace=namespace,
        type="group",
        name="backend",
        is_private=True,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch1_obj)
    await channel_repo.create(ch2_obj)

    got = await channel_repo.get(ch1)
    assert got is not None
    assert got.name == "general"
    assert got.namespace == namespace

    by_ns = await channel_repo.list_by_namespace(namespace, company_id=company_id)
    assert {c.channel_id for c in by_ns} == {ch1, ch2}

    deleted = await channel_repo.delete(ch2)
    assert deleted is True
    assert await channel_repo.get(ch2) is None


@pytest.mark.asyncio
async def test_channel_members(
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Управление участниками канала."""
    ch_mbr = f"{unique_id}_ch_mbr"

    ch = SyncChannel(
        channel_id=ch_mbr,
        company_id=company_id,
        namespace=f"ns_{unique_id}_mbr",
        type="topic",
        name="test",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await channel_repo.create(ch)

    assert await channel_repo.is_member(ch_mbr, "user_10", company_id=company_id) is False

    await channel_repo.upsert_member(ch_mbr, "user_10", "member", company_id)
    assert await channel_repo.is_member(ch_mbr, "user_10", company_id=company_id) is True

    await channel_repo.add_member_if_missing(ch_mbr, "user_10", "admin", company_id)
    assert await channel_repo.is_member(ch_mbr, "user_10", company_id=company_id) is True


@pytest.mark.asyncio
async def test_list_for_user_filters_by_membership(
    channel_repo: ChannelRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    namespace = f"ns_{unique_id}_u"
    ch_topic = f"{unique_id}_ch_topic"
    ch_dm = f"{unique_id}_ch_dm"
    ch_secret = f"{unique_id}_ch_secret"

    ch_in_namespace = SyncChannel(
        channel_id=ch_topic,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name="a",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    ch_direct = SyncChannel(
        channel_id=ch_dm,
        company_id=company_id,
        namespace="default",
        type="direct",
        name=None,
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="alice",
    )
    ch_other = SyncChannel(
        channel_id=ch_secret,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name="b",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="bob",
    )
    await channel_repo.create(ch_in_namespace)
    await channel_repo.create(ch_direct)
    await channel_repo.create(ch_other)

    await channel_repo.upsert_member(ch_topic, "alice", "member", company_id)
    await channel_repo.upsert_member(ch_dm, "alice", "owner", company_id)
    await channel_repo.upsert_member(ch_secret, "bob", "member", company_id)

    alice_all = await channel_repo.list_for_user(
        "alice", company_id=company_id, namespace=None
    )
    assert {c.channel_id for c in alice_all} == {ch_topic, ch_dm}

    alice_in_ns = await channel_repo.list_for_user(
        "alice", company_id=company_id, namespace=namespace
    )
    assert [c.channel_id for c in alice_in_ns] == [ch_topic]

    ids = await channel_repo.list_member_user_ids(ch_dm, company_id=company_id)
    assert "alice" in ids
