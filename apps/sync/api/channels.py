"""API роутер для каналов (Channels)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.container import get_sync_container
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelRead,
    ChannelUpdate,
)
from apps.sync.models.common import PaginationRequest
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.events import event_channel_member_added
from apps.sync.realtime.publish_events import publish_realtime_events
from apps.sync.realtime.tasks import handle_command
from core.context import get_context

router = APIRouter()


@router.get("/")
async def list_channels(
    space_id: str | None = None,
    pagination: PaginationRequest = Depends(),
) -> list[ChannelRead]:
    """Список каналов текущего пользователя (членство). Опционально фильтр по space_id."""
    context = get_context()
    container = get_sync_container()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id
    channels = await container.channel_repository.list_for_user(
        viewer_id,
        space_id=space_id,
        limit=pagination.limit,
        company_id=company_id,
    )
    channel_ids = [c.channel_id for c in channels]
    summaries = await container.message_repository.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=channel_ids,
        viewer_user_id=viewer_id,
    )
    out: list[ChannelRead] = []
    for c in channels:
        summ = summaries[c.channel_id]
        out.append(
            await channel_read_from_entity(
                c,
                viewer_user_id=viewer_id,
                channel_repository=container.channel_repository,
                user_repository=container.user_repository,
                company_id=company_id,
                lane_summary=summ,
            )
        )
    return out


@router.patch("/{channel_id}")
async def update_channel(channel_id: str, body: ChannelUpdate) -> ChannelRead:
    """Обновление канала (команда в процессе API)."""
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="channels.update",
        payload={"channel_id": channel_id, "body": body.model_dump(exclude_unset=True)},
    )
    out = await dispatch_sync_command(cmd)
    if not out.get("ok"):
        raise RuntimeError(f"Command failed: {out.get('error_detail')}")
    return ChannelRead.model_validate(out["result"])


@router.post("/{channel_id}/read", status_code=204)
async def mark_channel_read(channel_id: str) -> None:
    """Отмечает основную ленту канала прочитанной для текущего пользователя."""
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="channels.mark_read",
        payload={"channel_id": channel_id},
    )
    body = await dispatch_sync_command(cmd)
    if not body.get("ok"):
        raise RuntimeError(f"Command failed: {body.get('error_detail')}")


@router.post("/", status_code=201)
async def create_channel(body: ChannelCreate) -> ChannelRead:
    """Создание канала через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="channels.create",
        payload={"body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(timeout=300.0)
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return ChannelRead.model_validate(res.return_value["result"])


@router.get("/{channel_id}/members", response_model=list[ChannelMemberRead])
async def list_channel_members(channel_id: str) -> list[ChannelMemberRead]:
    """Участники канала (только для состоящих в канале)."""
    context = get_context()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id
    container = get_sync_container()
    ch = await container.channel_repository.get(channel_id)
    if ch is None or ch.company_id != company_id:
        raise HTTPException(status_code=404, detail="Канал не найден.")
    if not await container.channel_repository.is_member(channel_id, viewer_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к каналу.")
    rows = await container.channel_repository.list_member_rows(channel_id, company_id=company_id)
    return [ChannelMemberRead(user_id=uid, role=role) for uid, role in rows]


@router.post("/{channel_id}/members", status_code=201)
async def add_member(channel_id: str, body: ChannelMemberAdd) -> ChannelMemberRead:
    """Добавление участника в канал (только участники канала)."""
    context = get_context()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id
    container = get_sync_container()
    ch = await container.channel_repository.get(channel_id)
    if ch is None or ch.company_id != company_id:
        raise HTTPException(status_code=404, detail="Канал не найден.")
    if not await container.channel_repository.is_member(channel_id, viewer_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к каналу.")
    await container.channel_repository.upsert_member(
        channel_id, body.user_id, body.role,
        company_id=company_id,
    )
    await publish_realtime_events([event_channel_member_added(channel_id, body.user_id)])
    return ChannelMemberRead(user_id=body.user_id, role=body.role)
