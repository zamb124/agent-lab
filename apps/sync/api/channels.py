"""API роутер для каналов (Channels)."""

from fastapi import APIRouter, Depends

from apps.sync.container import get_sync_container
from apps.sync.models.channels import ChannelRead, ChannelCreate, ChannelMemberAdd, ChannelMemberRead
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
    """Список каналов (опционально фильтр по space_id)."""
    context = get_context()
    container = get_sync_container()
    if space_id:
        channels = await container.channel_repository.list_by_space(
            space_id, limit=pagination.limit,
            company_id=context.active_company.company_id,
        )
    else:
        channels = await container.channel_repository.list_all(
            limit=pagination.limit,
            company_id=context.active_company.company_id,
        )
    return [
        ChannelRead(
            id=c.channel_id,
            space_id=c.space_id,
            type=c.type,
            name=c.name,
            is_private=c.is_private,
            created_at=c.created_at,
            created_by_user_id=c.created_by_user_id,
        )
        for c in channels
    ]


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
