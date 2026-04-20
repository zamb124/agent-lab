"""REST-зеркала команд spaces. Тонкие обвязки над `op_spaces_*`."""

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from apps.sync.models.spaces import SpaceCreate, SpaceRead, SpaceUpdate
from apps.sync.realtime.operations import (
    SpacesCreatePayload,
    SpacesListPayload,
    SpacesUpdatePayload,
    op_spaces_create,
    op_spaces_list,
    op_spaces_update,
)
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter()


@router.get("/", response_model=OffsetPage[SpaceRead])
async def list_spaces(
    container: ContainerDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage[SpaceRead]:
    user = get_context().user
    result = await op_spaces_list(
        SpacesListPayload(limit=limit, offset=offset),
        user=user,
        container=container,
    )
    return OffsetPage[SpaceRead](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )


@router.post("/", status_code=201, response_model=SpaceRead)
async def create_space(container: ContainerDep, body: SpaceCreate) -> SpaceRead:
    user = get_context().user
    return await op_spaces_create(
        SpacesCreatePayload(body=body), user=user, container=container
    )


@router.patch("/{space_id}", response_model=SpaceRead)
async def update_space(
    container: ContainerDep, space_id: str, body: SpaceUpdate
) -> SpaceRead:
    user = get_context().user
    return await op_spaces_update(
        SpacesUpdatePayload(space_id=space_id, body=body),
        user=user,
        container=container,
    )
