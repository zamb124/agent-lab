"""Дополнительные сценарии ChannelRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncChannel
from apps.sync.db.repositories.channel_repository import ChannelRepository


@pytest.mark.asyncio
async def test_list_by_namespace_and_list_for_user_with_namespace_filter(
    channel_repo: ChannelRepository,
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
    await channel_repo.create(ch1_obj)
    await channel_repo.create(ch2_obj)
    await channel_repo.upsert_member(ch1, "alice", "member", company_id=company_id)
    await channel_repo.upsert_member(ch2, "alice", "member", company_id=company_id)

    by_ns = await channel_repo.list_by_namespace(namespace, company_id=company_id)
    assert {c.channel_id for c in by_ns} == {ch1, ch2}

    for_user = await channel_repo.list_for_user("alice", namespace=namespace, company_id=company_id)
    assert {c.channel_id for c in for_user} == {ch1, ch2}


@pytest.mark.asyncio
async def test_is_member_and_get_member_role_explicit_company(
    channel_repo: ChannelRepository,
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
    await channel_repo.create(ch)
    await channel_repo.upsert_member(ch_m, "bob", "admin", company_id=company_id)
    assert await channel_repo.is_member(ch_m, "bob", company_id=company_id) is True
    assert await channel_repo.is_member(ch_m, "nobody", company_id=company_id) is False
    assert await channel_repo.get_member_role(ch_m, "bob") == "admin"


@pytest.mark.asyncio
async def test_set_member_last_read_at_errors(
    channel_repo: ChannelRepository,
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
    await channel_repo.create(ch)
    at = datetime.now(tz=UTC)
    with pytest.raises(ValueError, match="не найден"):
        await channel_repo.set_member_last_read_at(ch_lr, "ghost", at, company_id=company_id)


@pytest.mark.asyncio
async def test_set_pinned_message_ids(
    channel_repo: ChannelRepository,
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
    await channel_repo.create(ch)
    await channel_repo.set_pinned_message_ids(ch_pin, [m1, m2], company_id=company_id)
    loaded = await channel_repo.get(ch_pin)
    assert loaded is not None
    assert loaded.pinned_message_ids == [m1, m2]


@pytest.mark.asyncio
async def test_list_member_user_ids(
    channel_repo: ChannelRepository,
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
    await channel_repo.create(ch)
    await channel_repo.upsert_member(ch_mem, "a", "owner", company_id=company_id)
    await channel_repo.upsert_member(ch_mem, "b", "member", company_id=company_id)
    ids = await channel_repo.list_member_user_ids(ch_mem, company_id=company_id)
    assert set(ids) == {"a", "b"}
