"""Дополнительные сценарии ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.models.channel import SyncChannel
from apps.sync.models.channel_member import SyncChannelMember


@pytest.mark.asyncio
async def test_list_by_namespace_and_list_for_user_with_namespace_filter(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    namespace = f"ns_{unique_id}_l"
    ch1 = f"{unique_id}_ch_1"
    ch2 = f"{unique_id}_ch_2"
    ch1_obj = SyncChannel(
        channel_id=ch1,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name="a",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    ch2_obj = SyncChannel(
        channel_id=ch2,
        company_id=company_id,
        namespace=namespace,
        type="topic",
        name="b",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch1_obj)
    _ = await SyncChannel.objects.create(instance=ch2_obj)
    await SyncChannelMember.ensure_channel_member_row(ch1, "alice", company_id=company_id)
    await SyncChannelMember.ensure_channel_member_row(ch2, "alice", company_id=company_id)

    by_ns = await SyncChannel.list_channels_in_namespace(
        namespace, company_id=company_id, limit=100, offset=0
    )
    assert {c.channel_id for c in by_ns} == {ch1, ch2}

    for_user = await SyncChannel.list_channels_for_user(
        "alice",
        namespace=namespace,
        company_id=company_id,
        limit=100,
        offset=0,
    )
    assert {c.channel_id for c in for_user} == {ch1, ch2}


@pytest.mark.asyncio
async def test_ensure_member_row_and_list_user_ids_explicit_company(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    ch_m = f"{unique_id}_ch_m"
    ch = SyncChannel(
        channel_id=ch_m,
        company_id=company_id,
        namespace="default",
        type="group",
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    await SyncChannelMember.ensure_channel_member_row(ch_m, "bob", company_id=company_id)
    ids = await SyncChannelMember.list_channel_member_user_ids(ch_m, company_id=company_id)
    assert ids == ["bob"]


@pytest.mark.asyncio
async def test_set_member_last_read_at_errors(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    ch_lr = f"{unique_id}_ch_lr"
    ch = SyncChannel(
        channel_id=ch_lr,
        company_id=company_id,
        namespace="default",
        type="group",
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    at = datetime.now(tz=UTC)
    with pytest.raises(ValueError, match="Channel member not found"):
        await SyncChannelMember.set_channel_member_last_read_at(
            ch_lr, "ghost", at, company_id=company_id
        )


@pytest.mark.asyncio
async def test_set_pinned_message_ids(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    ch_pin = f"{unique_id}_ch_pin"
    m1 = f"{unique_id}_m1"
    m2 = f"{unique_id}_m2"
    ch = SyncChannel(
        channel_id=ch_pin,
        company_id=company_id,
        namespace="default",
        type="group",
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    await SyncChannel.set_channel_pinned_message_ids(
        ch_pin, [m1, m2], company_id=company_id
    )
    loaded = await SyncChannel.get(ch_pin)
    assert loaded is not None
    assert loaded.pinned_message_ids == [m1, m2]


@pytest.mark.asyncio
async def test_list_settings_user_ids(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    ch_mem = f"{unique_id}_ch_mem"
    ch = SyncChannel(
        channel_id=ch_mem,
        company_id=company_id,
        namespace="default",
        type="group",
        name="g",
        is_private=False,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="u1",
    )
    _ = await SyncChannel.objects.create(instance=ch)
    await SyncChannelMember.ensure_channel_member_row(ch_mem, "a", company_id=company_id)
    await SyncChannelMember.ensure_channel_member_row(ch_mem, "b", company_id=company_id)
    ids = await SyncChannelMember.list_channel_member_user_ids(ch_mem, company_id=company_id)
    assert set(ids) == {"a", "b"}
