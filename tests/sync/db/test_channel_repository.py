"""Тесты ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.channel import SyncChannel
from apps.sync.models.channel_member import SyncChannelMember


@pytest.mark.asyncio
async def test_channel_crud(
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
    _ = await SyncChannel.objects.create(instance=ch1_obj)
    _ = await SyncChannel.objects.create(instance=ch2_obj)

    got = await SyncChannel.get(ch1)
    assert got is not None
    assert got.name == "general"
    assert got.namespace == namespace

    by_ns = await SyncChannel.list_channels_in_namespace(
        namespace, company_id=company_id, limit=100, offset=0
    )
    assert {c.channel_id for c in by_ns} == {ch1, ch2}

    deleted = await SyncChannel.delete_by_id(ch2)
    assert deleted is True
    assert await SyncChannel.get(ch2) is None


@pytest.mark.asyncio
async def test_channel_members(
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
    _ = await SyncChannel.objects.create(instance=ch)

    ids_before = await SyncChannelMember.list_channel_member_user_ids(ch_mbr, company_id=company_id
    )
    assert "user_10" not in ids_before

    await SyncChannelMember.ensure_channel_member_row(
        ch_mbr, "user_10", company_id=company_id
    )
    ids_after = await SyncChannelMember.list_channel_member_user_ids(ch_mbr, company_id=company_id
    )
    assert "user_10" in ids_after

    await SyncChannelMember.ensure_channel_member_row(
        ch_mbr, "user_10", company_id=company_id
    )
    ids_idempotent = await SyncChannelMember.list_channel_member_user_ids(ch_mbr, company_id=company_id
    )
    assert ids_idempotent.count("user_10") == 1


@pytest.mark.asyncio
async def test_list_for_user_filters_by_membership(
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
    _ = await SyncChannel.objects.create(instance=ch_in_namespace)
    _ = await SyncChannel.objects.create(instance=ch_direct)
    _ = await SyncChannel.objects.create(instance=ch_other)

    await SyncChannelMember.ensure_channel_member_row(ch_topic, "alice", company_id=company_id)
    await SyncChannelMember.ensure_channel_member_row(ch_dm, "alice", company_id=company_id)
    await SyncChannelMember.ensure_channel_member_row(ch_secret, "bob", company_id=company_id)

    alice_all = await SyncChannel.list_channels_for_user(
        "alice",
        company_id=company_id,
        namespace=None,
        limit=100,
        offset=0,
    )
    assert {c.channel_id for c in alice_all} == {ch_topic, ch_dm}

    alice_in_ns = await SyncChannel.list_channels_for_user(
        "alice",
        company_id=company_id,
        namespace=namespace,
        limit=100,
        offset=0,
    )
    assert [c.channel_id for c in alice_in_ns] == [ch_topic]

    ids = await SyncChannelMember.list_channel_member_user_ids(ch_dm, company_id=company_id
    )
    assert "alice" in ids
