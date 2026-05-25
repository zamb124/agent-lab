"""REST-зеркала команд threads. Тонкие обвязки над `op_threads_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from apps.sync.models.threads import ThreadCreate, ThreadRead, ThreadRow
from apps.sync.realtime.context import require_current_user
from apps.sync.realtime.operations import (
    ThreadsCreatePayload,
    ThreadsItemPayload,
    ThreadsListPayload,
    op_threads_create,
    op_threads_item,
    op_threads_list,
)
from core.pagination import OffsetPage

router = APIRouter()


@router.get("/", response_model=OffsetPage[ThreadRow])
async def list_threads(
    channel_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ThreadRow]:
    user = require_current_user()
    result = await op_threads_list(
        ThreadsListPayload(channel_id=channel_id, limit=limit, offset=offset),
        user=user,
        container=container,
    )
    return OffsetPage[ThreadRow](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )


@router.post("/", status_code=201, response_model=ThreadRead)
async def create_thread(
    container: ContainerDep, channel_id: str, body: ThreadCreate
) -> ThreadRead:
    _ = channel_id
    user = require_current_user()
    return await op_threads_create(
        ThreadsCreatePayload(body=body), user=user, container=container
    )


@router.get("/{thread_id}", response_model=ThreadRow)
async def get_thread(thread_id: str, container: ContainerDep) -> ThreadRow:
    user = require_current_user()
    return await op_threads_item(
        ThreadsItemPayload(thread_id=thread_id), user=user, container=container
    )
