"""REST-зеркала команд git_resources. Тонкие обвязки над `op_git_resources_*`."""

from fastapi import APIRouter

from apps.sync.dependencies import ContainerDep
from apps.sync.models.git import GitResourceRefCreate, GitResourceRefRead
from apps.sync.realtime.operations import (
    GitResourcesGetPayload,
    GitResourcesUpsertPayload,
    op_git_resources_get,
    op_git_resources_upsert,
)
from core.context import get_context

router = APIRouter()


@router.post("/resources", status_code=201, response_model=GitResourceRefRead)
async def upsert_git_resource(
    container: ContainerDep, body: GitResourceRefCreate
) -> GitResourceRefRead:
    user = get_context().user
    return await op_git_resources_upsert(
        GitResourcesUpsertPayload(body=body), user=user, container=container
    )


@router.get("/resources/{git_ref_id}", response_model=GitResourceRefRead)
async def get_git_resource(
    git_ref_id: str, container: ContainerDep
) -> GitResourceRefRead:
    user = get_context().user
    return await op_git_resources_get(
        GitResourcesGetPayload(git_ref_id=git_ref_id),
        user=user,
        container=container,
    )
