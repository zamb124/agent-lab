"""Интеграционные тесты обработчиков call.* команд.

Используются реальные репозитории и реальная БД. Паттерн из test_handlers_execute_command.py.
notification_manager.publish вызывает реальный Redis (из docker-compose-test).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.container import get_sync_container
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command


def _cmd(actor: str, company_id: str, typ: str, payload: dict) -> CommandEnvelope:
    return CommandEnvelope(
        id=uuid4().hex,
        actor_user_id=actor,
        company_id=company_id,
        type=typ,
        payload=payload,
    )


async def _setup_channel_with_members(
    *,
    company_id: str,
    space_repo: SpaceRepository,
    channel_repo: ChannelRepository,
    call_repo: CallRepository,
    unique_id: str,
    members: list[str],
) -> str:
    """Создаёт space + channel + добавляет участников. Возвращает channel_id."""
    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    sr = await execute_command(
        _cmd("u1", company_id, "spaces.create", {"body": {"name": f"Sp-{unique_id}", "description": None}}),
        **repos,
    )
    assert sr.ok

    cr = await execute_command(
        _cmd("u1", company_id, "channels.create", {
            "body": {"name": f"ch-{unique_id}", "type": "topic", "space_id": sr.result.id}
        }),
        **repos,
    )
    assert cr.ok

    for uid in members:
        if uid != "u1":
            await channel_repo.upsert_member(cr.result.id, uid, "member", company_id=company_id)

    return cr.result.id


@pytest.mark.asyncio
async def test_call_invite_sfu_two_members(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Два участника → SFU (P2P_MAX=0, все звонки через LiveKit)."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1", "member1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    result = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    assert result.ok
    assert result.result.mode == "sfu"
    assert result.result.livekit_room_name is not None
    assert result.result.status == "ringing"
    assert len(result.result.participants) == 2
    statuses = {p.user_id: p.status for p in result.result.participants}
    assert statuses["u1"] == "joined"
    assert statuses["member1"] == "invited"
    assert result.result.call_type == "video"

    msg_events = [e for e in result.events if e.type == "sync/message/created"]
    assert len(msg_events) == 1
    payload = msg_events[0].payload
    contents = payload.get("contents") if isinstance(payload, dict) else None
    assert isinstance(contents, list)
    boundary_blocks = [c for c in contents if isinstance(c, dict) and c.get("type") == "call/boundary"]
    assert len(boundary_blocks) == 1
    data = boundary_blocks[0].get("data") or {}
    assert data.get("phase") == "started"
    assert data.get("call_id") == result.result.call_id


@pytest.mark.asyncio
async def test_call_invite_legacy_audio_payload_yields_video_read(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Старый клиент с call_type audio: ответ CallRead всегда с единым типом video."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=f"{unique_id}-legacy-audio",
        members=["u1", "member1"],
    )
    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )
    result = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "audio"}),
        **repos,
    )
    assert result.ok
    assert result.result.call_type == "video"


@pytest.mark.asyncio
async def test_call_invite_sfu_three_members(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Три участника → SFU (как и все остальные, P2P_MAX=0)."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1", "member1", "u_other"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    result = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    assert result.ok
    assert result.result.mode == "sfu"
    assert result.result.livekit_room_name is not None


@pytest.mark.asyncio
async def test_call_invite_replaces_existing(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Повторный invite завершает существующий звонок и создаёт новый."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1", "member1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    r1 = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    assert r1.ok
    first_call_id = r1.result.call_id

    r2 = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    assert r2.ok
    assert r2.result.call_id != first_call_id

    old_call = await call_repo.get_call(first_call_id, company_id)
    assert old_call.status == "ended"


@pytest.mark.asyncio
async def test_call_accept_and_hangup(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Accept меняет статус участника, hangup завершает звонок при отсутствии joined."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1", "member1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    invite_res = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    call_id = invite_res.result.call_id

    accept_res = await execute_command(
        _cmd("member1", company_id, "call.accept", {"call_id": call_id}),
        **repos,
    )
    assert accept_res.ok
    assert accept_res.result.status == "active"
    accept_boundary_msgs = [e for e in accept_res.events if e.type == "sync/message/created"]
    assert len(accept_boundary_msgs) == 0

    hangup_res = await execute_command(
        _cmd("u1", company_id, "call.hangup", {"call_id": call_id}),
        **repos,
    )
    assert hangup_res.ok

    hangup_res2 = await execute_command(
        _cmd("member1", company_id, "call.hangup", {"call_id": call_id}),
        **repos,
    )
    assert hangup_res2.ok
    assert hangup_res2.result.status == "ended"


@pytest.mark.asyncio
async def test_call_invite_no_access_raises(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Пользователь не в канале — raise PermissionError."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    with pytest.raises(PermissionError):
        await execute_command(
            _cmd("outsider", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
            **repos,
        )


@pytest.mark.asyncio
async def test_call_decline(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Участник отклоняет звонок → статус 'declined', звонок остаётся ringing."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1", "member1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    invite_res = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    call_id = invite_res.result.call_id

    decline_res = await execute_command(
        _cmd("member1", company_id, "call.decline", {"call_id": call_id}),
        **repos,
    )
    assert decline_res.ok

    participants = await call_repo.list_participants(call_id)
    statuses = {p.user_id: p.status for p in participants}
    assert statuses["member1"] == "declined"
    assert statuses["u1"] == "joined"

    call = await call_repo.get_call(call_id, company_id)
    assert call.status == "ringing"


@pytest.mark.asyncio
async def test_call_hangup_ends_when_all_leave(
    call_repo: CallRepository,
    channel_repo: ChannelRepository,
    space_repo: SpaceRepository,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Когда все участники вышли — звонок переходит в ended."""
    channel_id = await _setup_channel_with_members(
        company_id=company_id,
        space_repo=space_repo,
        channel_repo=channel_repo,
        call_repo=call_repo,
        unique_id=unique_id,
        members=["u1"],
    )

    repos = dict(
        spaces=space_repo,
        channels=channel_repo,
        threads=ThreadRepository(db=call_repo._db),
        messages=MessageRepository(db=call_repo._db),
        git_refs=GitResourceRefRepository(db=call_repo._db),
        calls=call_repo,
        user_repository=get_sync_container().user_repository,
    )

    invite_res = await execute_command(
        _cmd("u1", company_id, "call.invite", {"channel_id": channel_id, "call_type": "video"}),
        **repos,
    )
    call_id = invite_res.result.call_id

    hangup_res = await execute_command(
        _cmd("u1", company_id, "call.hangup", {"call_id": call_id}),
        **repos,
    )
    assert hangup_res.ok
    assert hangup_res.result.status == "ended"

    call = await call_repo.get_call(call_id, company_id)
    assert call.status == "ended"
    assert call.ended_at is not None
