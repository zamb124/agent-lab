"""API роутер для каналов (Channels)."""

from fastapi import APIRouter, Depends

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.container import get_sync_container
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelRead,
)
from apps.sync.models.common import PaginationRequest
from apps.sync.realtime.commands import CommandEnvelope
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
    out: list[ChannelRead] = []
    for c in channels:
        out.append(
            await channel_read_from_entity(
                c,
                viewer_user_id=viewer_id,
                channel_repository=container.channel_repository,
                user_repository=container.user_repository,
                company_id=company_id,
            )
        )
    return out


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


@router.post("/{channel_id}/members", status_code=201)
async def add_member(channel_id: str, body: ChannelMemberAdd) -> ChannelMemberRead:
    """Добавление участника в канал."""
    context = get_context()
    container = get_sync_container()
    await container.channel_repository.upsert_member(
        channel_id, body.user_id, body.role,
        company_id=context.active_company.company_id,
    )
    return ChannelMemberRead(user_id=body.user_id, role=body.role)
