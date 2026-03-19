"""API роутер для пространств (Spaces)."""

from fastapi import APIRouter, Depends

from apps.sync.container import get_sync_container
from apps.sync.models.common import PaginationRequest
from apps.sync.models.spaces import SpaceRead, SpaceCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.context import get_context

router = APIRouter()


@router.get("/")
async def list_spaces(pagination: PaginationRequest = Depends()) -> list[SpaceRead]:
    """Список пространств компании."""
    context = get_context()
    container = get_sync_container()
    spaces = await container.space_repository.list_all(
        limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    return [
        SpaceRead(
            id=s.space_id,
            name=s.name,
            description=s.description,
            created_at=s.created_at,
            created_by_user_id=s.created_by_user_id,
        )
        for s in spaces
    ]


@router.post("/", status_code=201)
async def create_space(body: SpaceCreate) -> SpaceRead:
    """Создание пространства через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="spaces.create",
        payload={"body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(timeout=300.0)
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return SpaceRead.model_validate(res.return_value["result"])
