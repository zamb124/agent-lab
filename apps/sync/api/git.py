"""REST-зеркала команд git_resources. Тонкие обвязки над `op_git_resources_*`."""

from fastapi import APIRouter

from apps.sync.di import Di
from apps.sync.models.git import GitResourceRefCreate, GitResourceRefRead
from apps.sync.realtime.operations import (
    GitResourcesGetPayload,
    GitResourcesUpsertPayload,
    op_git_resources_get,
    op_git_resources_upsert,
)
from core.context import require_context

router = APIRouter()


@router.post("/resources", status_code=201, response_model=GitResourceRefRead)
async def upsert_git_resource(
    di: Di, body: GitResourceRefCreate
) -> GitResourceRefRead:
    user = require_context().user
    return await op_git_resources_upsert(
        GitResourcesUpsertPayload(body=body), user=user, di=di
    )


@router.get("/resources/{git_ref_id:path}", response_model=GitResourceRefRead)
async def get_git_resource(
    git_ref_id: str, di: Di
) -> GitResourceRefRead:
    user = require_context().user
    return await op_git_resources_get(
        GitResourcesGetPayload(git_ref_id=git_ref_id),
        user=user,
        di=di,
    )
