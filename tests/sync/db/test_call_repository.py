"""Интеграционные тесты CallRepository — реальная sync БД, без моков."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.sync.db.models import SyncCall, SyncCallLink, SyncCallParticipant
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.models.spaces import SpaceCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command


def _make_call(channel_id: str, company_id: str, *, mode: str = "p2p") -> SyncCall:
    return SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=channel_id,
        mode=mode,
        call_type="video",
        status="ringing",
        created_by_user_id="user1",
    )


def _make_participant(call_id: str, user_id: str, *, status: str = "invited") -> SyncCallParticipant:
    return SyncCallParticipant(
        id=uuid4().hex,
        call_id=call_id,
        user_id=user_id,
        status=status,
    )


@pytest.mark.asyncio
async def test_create_and_get_call(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    cmd_space = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="spaces.create", payload={"body": {"name": f"Space-{unique_id}", "description": None}},
    )
    from apps.sync.db.repositories.channel_repository import ChannelRepository as CR
    from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
    from apps.sync.db.repositories.message_repository import MessageRepository
    from apps.sync.db.repositories.thread_repository import ThreadRepository

    space_result = await execute_command(
        cmd_space,
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    assert space_result.ok

    cmd_ch = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="channels.create",
        payload={"body": {"name": f"ch-{unique_id}", "type": "topic", "space_id": space_result.result.id}},
    )
    ch_result = await execute_command(
        cmd_ch,
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    assert ch_result.ok
    channel_id = ch_result.result.id

    call = _make_call(channel_id, company_id, mode="sfu")
    created = await call_repo.create_call(call)
    assert created.call_id == call.call_id
    assert created.status == "ringing"

    fetched = await call_repo.get_call(call.call_id, company_id)
    assert fetched.call_id == call.call_id
    assert fetched.mode == "sfu"


@pytest.mark.asyncio
async def test_add_and_list_participants(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
    from apps.sync.db.repositories.message_repository import MessageRepository
    from apps.sync.db.repositories.thread_repository import ThreadRepository

    cmd_space = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="spaces.create", payload={"body": {"name": f"S-{unique_id}", "description": None}},
    )
    sr = await execute_command(
        cmd_space, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    cmd_ch = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="channels.create",
        payload={"body": {"name": f"c-{unique_id}", "type": "topic", "space_id": sr.result.id}},
    )
    cr = await execute_command(
        cmd_ch, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    channel_id = cr.result.id

    call = _make_call(channel_id, company_id)
    await call_repo.create_call(call)

    p1 = _make_participant(call.call_id, "user_a", status="joined")
    p2 = _make_participant(call.call_id, "user_b", status="invited")
    await call_repo.add_participant(p1)
    await call_repo.add_participant(p2)

    participants = await call_repo.list_participants(call.call_id)
    ids = {p.user_id for p in participants}
    assert "user_a" in ids
    assert "user_b" in ids
    assert await call_repo.count_active_participants(call.call_id) == 1


@pytest.mark.asyncio
async def test_update_call_status(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
    from apps.sync.db.repositories.message_repository import MessageRepository
    from apps.sync.db.repositories.thread_repository import ThreadRepository

    cmd_space = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="spaces.create", payload={"body": {"name": f"Sp-{unique_id}", "description": None}},
    )
    sr = await execute_command(
        cmd_space, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    cmd_ch = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="channels.create",
        payload={"body": {"name": f"ch2-{unique_id}", "type": "topic", "space_id": sr.result.id}},
    )
    cr = await execute_command(
        cmd_ch, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    channel_id = cr.result.id

    call = _make_call(channel_id, company_id)
    await call_repo.create_call(call)

    now = datetime.now(UTC)
    await call_repo.update_call_status(call.call_id, "active", started_at=now)

    updated = await call_repo.get_call(call.call_id, company_id)
    assert updated.status == "active"
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_get_active_call_for_channel_none(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    result = await call_repo.get_active_call_for_channel("nonexistent_channel", company_id)
    assert result is None


@pytest.mark.asyncio
async def test_call_link_create_and_get(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
    from apps.sync.db.repositories.message_repository import MessageRepository
    from apps.sync.db.repositories.thread_repository import ThreadRepository

    cmd_space = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="spaces.create", payload={"body": {"name": f"SpL-{unique_id}", "description": None}},
    )
    sr = await execute_command(
        cmd_space, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    cmd_ch = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="channels.create",
        payload={"body": {"name": f"chL-{unique_id}", "type": "topic", "space_id": sr.result.id}},
    )
    cr = await execute_command(
        cmd_ch, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    channel_id = cr.result.id

    link = SyncCallLink(
        link_token=uuid4().hex,
        channel_id=channel_id,
        company_id=company_id,
        call_type="video",
        created_by_user_id="user1",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    created_link = await call_repo.create_link(link)
    assert created_link.link_token == link.link_token

    fetched_link = await call_repo.get_link(link.link_token)
    assert fetched_link.channel_id == channel_id
    assert fetched_link.call_type == "video"


@pytest.mark.asyncio
async def test_expired_link_raises(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
    from apps.sync.db.repositories.message_repository import MessageRepository
    from apps.sync.db.repositories.thread_repository import ThreadRepository

    cmd_space = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="spaces.create", payload={"body": {"name": f"SpE-{unique_id}", "description": None}},
    )
    sr = await execute_command(
        cmd_space, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    cmd_ch = CommandEnvelope(
        id=uuid4().hex, actor_user_id="u1", company_id=company_id,
        type="channels.create",
        payload={"body": {"name": f"chE-{unique_id}", "type": "topic", "space_id": sr.result.id}},
    )
    cr = await execute_command(
        cmd_ch, spaces=space_repo, channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
    )
    channel_id = cr.result.id

    expired_link = SyncCallLink(
        link_token=uuid4().hex,
        channel_id=channel_id,
        company_id=company_id,
        call_type="video",
        created_by_user_id="user1",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await call_repo.create_link(expired_link)

    with pytest.raises(ValueError, match="истекла"):
        await call_repo.get_link(expired_link.link_token)
