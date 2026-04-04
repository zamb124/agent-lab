"""API роутер для Git-ресурсов."""

from fastapi import APIRouter, HTTPException

from apps.sync.container import get_sync_container
from apps.sync.models.git import GitResourceRefRead, GitResourceRefCreate
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.config import get_settings
from core.context import get_context

router = APIRouter()


@router.post("/resources", status_code=201)
async def upsert_git_resource(body: GitResourceRefCreate) -> GitResourceRefRead:
    """Создание/обновление Git-ресурса через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="git.resources.upsert",
        payload={"body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return GitResourceRefRead.model_validate(res.return_value["result"])


@router.get("/resources/{git_ref_id}")
async def get_git_resource(git_ref_id: str) -> GitResourceRefRead:
    """Получение Git-ресурса по ID."""
    container = get_sync_container()
    ref = await container.git_resource_ref_repository.get(git_ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Git resource not found")
    return GitResourceRefRead(
        id=ref.git_ref_id,
        provider=ref.provider,
        kind=ref.kind,
        project_key=ref.project_key,
        external_id=ref.external_id,
        url=ref.url,
        extra=ref.extra,
    )
