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

    by_ns = await SyncChannel.list_by_name_in_namespace_asc(
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

    ids_before = await SyncChannelMember.list_unordered_user_ids(ch_mbr, company_id=company_id
    )
    assert "user_10" not in ids_before

    await SyncChannelMember.ensure_member(
        ch_mbr, "user_10", company_id=company_id
    )
    ids_after = await SyncChannelMember.list_unordered_user_ids(ch_mbr, company_id=company_id
    )
    assert "user_10" in ids_after

    await SyncChannelMember.ensure_member(
        ch_mbr, "user_10", company_id=company_id
    )
    ids_idempotent = await SyncChannelMember.list_unordered_user_ids(ch_mbr, company_id=company_id
    )
    assert ids_idempotent.count("user_10") == 1
    assert await SyncChannelMember.is_notifications_muted(
        ch_mbr, "user_10", company_id=company_id
    ) is False
    await SyncChannelMember.update_notifications_muted(
        ch_mbr, "user_10", True, company_id=company_id
    )
    assert await SyncChannelMember.is_notifications_muted(
        ch_mbr, "user_10", company_id=company_id
    ) is True
    with pytest.raises(ValueError, match="Channel member not found"):
        await SyncChannelMember.update_notifications_muted(
            ch_mbr, "ghost", True, company_id=company_id
        )
    with pytest.raises(ValueError, match="Channel member not found"):
        _ = await SyncChannelMember.is_notifications_muted(
            ch_mbr, "user_10", company_id=f"other_{unique_id}"
        )
    with pytest.raises(ValueError, match="Member row belongs to another company"):
        await SyncChannelMember.ensure_member(
            ch_mbr, "user_10", company_id=f"other_{unique_id}"
        )
    assert await SyncChannelMember.delete_by_user(
        ch_mbr, "user_10", company_id=f"other_{unique_id}"
    ) is False
    assert "user_10" in await SyncChannelMember.list_unordered_user_ids(ch_mbr, company_id=company_id)
    assert await SyncChannelMember.delete_by_user(
        ch_mbr, "user_10", company_id=company_id
    ) is True
    assert "user_10" not in await SyncChannelMember.list_unordered_user_ids(ch_mbr, company_id=company_id)
    assert await SyncChannelMember.delete_by_user(
        ch_mbr, "user_10", company_id=company_id
    ) is False


@pytest.mark.asyncio
async def test_peer_last_read_at_returns_other_member_time(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = f"{unique_id}_peer"
    at = datetime(2026, 4, 1, tzinfo=UTC)
    await SyncChannelMember.ensure_member(channel_id, "viewer", company_id=company_id)
    assert await SyncChannelMember.peer_last_read_at(
        channel_id, "viewer", company_id=company_id
    ) is None
    await SyncChannelMember.ensure_member(channel_id, "peer", company_id=company_id)
    assert await SyncChannelMember.peer_last_read_at(
        channel_id, "viewer", company_id=company_id
    ) is None
    await SyncChannelMember.update_last_read_at(
        channel_id, "peer", at, company_id=company_id
    )
    assert await SyncChannelMember.peer_last_read_at(
        channel_id, "viewer", company_id=company_id
    ) == at
    assert await SyncChannelMember.peer_last_read_at(
        channel_id, "viewer", company_id=f"other_{unique_id}"
    ) is None


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

    await SyncChannelMember.ensure_member(ch_topic, "alice", company_id=company_id)
    await SyncChannelMember.ensure_member(ch_dm, "alice", company_id=company_id)
    await SyncChannelMember.ensure_member(ch_secret, "bob", company_id=company_id)

    alice_all = await SyncChannel.list_member_channels_by_type_and_name_asc(
        "alice",
        company_id=company_id,
        namespace=None,
        limit=100,
        offset=0,
    )
    assert {c.channel_id for c in alice_all} == {ch_topic, ch_dm}

    alice_in_ns = await SyncChannel.list_member_channels_by_type_and_name_asc(
        "alice",
        company_id=company_id,
        namespace=namespace,
        limit=100,
        offset=0,
    )
    assert [c.channel_id for c in alice_in_ns] == [ch_topic]

    ids = await SyncChannelMember.list_unordered_user_ids(ch_dm, company_id=company_id
    )
    assert "alice" in ids


@pytest.mark.asyncio
async def test_list_by_name_filters_company_and_orders_by_name(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    alpha_id = f"{unique_id}_alpha"
    beta_id = f"{unique_id}_beta"
    foreign_id = f"{unique_id}_foreign"
    namespace = f"ns_{unique_id}_name"
    now = datetime.now(tz=UTC)
    alpha = SyncChannel(
        channel_id=alpha_id,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name=f"Alpha {unique_id}",
        is_private=False,
        created_at=now,
        created_by_user_id="user_1",
    )
    beta = SyncChannel(
        channel_id=beta_id,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name=f"Beta {unique_id}",
        is_private=False,
        created_at=now,
        created_by_user_id="user_1",
    )
    foreign = SyncChannel(
        channel_id=foreign_id,
        company_id=f"other_{unique_id}",
        namespace=namespace,
        type="topic",
        name=f"Alpha {unique_id}",
        is_private=False,
        created_at=now,
        created_by_user_id="user_1",
    )
    _ = await SyncChannel.objects.create(instance=alpha)
    _ = await SyncChannel.objects.create(instance=beta)
    _ = await SyncChannel.objects.create(instance=foreign)

    found = await SyncChannel.list_by_name_asc(company_id, unique_id, limit=20)
    assert [row.channel_id for row in found] == [alpha_id, beta_id]
    limited = await SyncChannel.list_by_name_asc(company_id, "", limit=1)
    assert [row.channel_id for row in limited] == [alpha_id]


@pytest.mark.asyncio
async def test_list_for_both_members_returns_shared_channels(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    shared_group = f"{unique_id}_shared_group"
    shared_topic = f"{unique_id}_shared_topic"
    only_alice = f"{unique_id}_only_alice"
    foreign_shared = f"{unique_id}_foreign_shared"
    now = datetime.now(tz=UTC)
    namespace = f"ns_{unique_id}_both"
    other_company = f"other_{unique_id}"
    for channel_id, owner_company, channel_type, name in (
        (shared_topic, company_id, "topic", "a"),
        (shared_group, company_id, "group", "b"),
        (only_alice, company_id, "direct", "c"),
        (foreign_shared, other_company, "group", "a"),
    ):
        _ = await SyncChannel.objects.create(
            instance=SyncChannel(
                channel_id=channel_id,
                company_id=owner_company,
                namespace=namespace,
                type=channel_type,
                name=name,
                is_private=False,
                created_at=now,
                created_by_user_id="alice",
            )
        )
    await SyncChannelMember.ensure_member(shared_group, "alice", company_id=company_id)
    await SyncChannelMember.ensure_member(shared_group, "bob", company_id=company_id)
    await SyncChannelMember.ensure_member(shared_topic, "alice", company_id=company_id)
    await SyncChannelMember.ensure_member(shared_topic, "bob", company_id=company_id)
    await SyncChannelMember.ensure_member(only_alice, "alice", company_id=company_id)
    await SyncChannelMember.ensure_member(foreign_shared, "alice", company_id=other_company)
    await SyncChannelMember.ensure_member(foreign_shared, "bob", company_id=other_company)

    found = await SyncChannel.list_for_both_members_by_type_and_name_asc(
        "alice", "bob", company_id=company_id, limit=10, offset=0
    )
    assert [row.channel_id for row in found] == [shared_group, shared_topic]
    limited = await SyncChannel.list_for_both_members_by_type_and_name_asc(
        "alice", "bob", company_id=company_id, limit=1, offset=0
    )
    assert [row.channel_id for row in limited] == [shared_group]
    assert await SyncChannel.list_for_both_members_by_type_and_name_asc(
        "alice", "carol", company_id=company_id, limit=10, offset=0
    ) == []


@pytest.mark.asyncio
async def test_find_in_company_returns_channel_or_none(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = f"{unique_id}_find"
    now = datetime.now(tz=UTC)
    _ = await SyncChannel.objects.create(
        instance=SyncChannel(
            channel_id=channel_id,
            company_id=company_id,
            namespace=f"ns_{unique_id}_find",
            type="topic",
            name="find",
            is_private=False,
            created_at=now,
            created_by_user_id="alice",
        )
    )

    found = await SyncChannel.by_channel_id(company_id, channel_id)
    assert found is not None
    assert found.channel_id == channel_id
    assert await SyncChannel.by_channel_id(f"other_{unique_id}", channel_id) is None
    assert await SyncChannel.by_channel_id(company_id, f"missing_{unique_id}") is None


@pytest.mark.asyncio
async def test_update_name_persists_channel_name(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = f"{unique_id}_rename"
    now = datetime.now(tz=UTC)
    stored = await SyncChannel.objects.create(
        instance=SyncChannel(
            channel_id=channel_id,
            company_id=company_id,
            namespace=f"ns_{unique_id}_rename",
            type="topic",
            name="before",
            is_private=False,
            created_at=now,
            created_by_user_id="alice",
        )
    )
    renamed = await SyncChannel.update_name(stored, f"after-{unique_id}")
    assert renamed.name == f"after-{unique_id}"
    loaded = await SyncChannel.by_channel_id(company_id, channel_id)
    assert loaded is not None
    assert loaded.name == f"after-{unique_id}"
