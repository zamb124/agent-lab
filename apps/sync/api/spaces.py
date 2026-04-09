"""API роутер для пространств (Spaces)."""

import uuid

from fastapi import APIRouter, Depends

from apps.sync.dependencies import ContainerDep
from apps.sync.models.common import PaginationRequest
from apps.sync.models.spaces import SpaceRead, SpaceCreate, SpaceUpdate
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.config import get_settings
from core.context import get_context

router = APIRouter()


@router.get("/")
async def list_spaces(container: ContainerDep, pagination: PaginationRequest = Depends()) -> list[SpaceRead]:
    """Список пространств компании."""
    context = get_context()
    spaces = await container.space_repository.list_all(
        limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    return [
        SpaceRead(
            id=s.space_id,
            name=s.name,
            description=s.description,
            avatar_url=s.avatar_url,
            namespace=s.namespace,
            created_at=s.created_at,
            created_by_user_id=s.created_by_user_id,
            transcribe_voice_messages=s.transcribe_voice_messages,
            speech_to_chat_enabled=s.speech_to_chat_enabled,
        )
        for s in spaces
    ]


@router.post("/", status_code=201)
async def create_space(container: ContainerDep, body: SpaceCreate) -> SpaceRead:
    """Создание пространства через TaskIQ."""
    _ = container
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="spaces.create",
        payload={"body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return SpaceRead.model_validate(res.return_value["result"])


@router.patch("/{space_id}")
async def update_space(container: ContainerDep, space_id: str, body: SpaceUpdate) -> SpaceRead:
    """Обновление пространства (команда в процессе API)."""
    _ = container
    context = get_context()
    cmd = CommandEnvelope(
        id=uuid.uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="spaces.update",
        payload={"space_id": space_id, "body": body.model_dump(exclude_unset=True)},
    )
    out = await dispatch_sync_command(cmd)
    if not out.get("ok"):
        raise RuntimeError(f"Command failed: {out.get('error_detail')}")
    return SpaceRead.model_validate(out["result"])
