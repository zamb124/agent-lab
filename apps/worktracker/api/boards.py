"""REST API досок задач — тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.models.api import BoardCreateRequest, BoardUpdateRequest
from apps.worktracker.realtime.operations import (
    BoardIdPayload,
    BoardsListPayload,
    BoardUpdatePayload,
    op_boards_create,
    op_boards_get,
    op_boards_list,
    op_boards_update,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.worktracker.models import Board

router = APIRouter(prefix="/boards", tags=["boards"])


@router.get("", response_model=OffsetPage[Board])
async def list_boards(
    container: ContainerDep,
    namespace: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[Board]:
    return await op_boards_list(
        BoardsListPayload(namespace=namespace, limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.get("/{board_id}", response_model=Board)
async def get_board(container: ContainerDep, board_id: str) -> Board:
    return await op_boards_get(
        BoardIdPayload(board_id=board_id),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=Board, status_code=201)
async def create_board(container: ContainerDep, body: BoardCreateRequest) -> Board:
    return await op_boards_create(body, user=require_context().user, container=container)


@router.patch("/{board_id}", response_model=Board)
async def update_board(
    container: ContainerDep, board_id: str, body: BoardUpdateRequest
) -> Board:
    return await op_boards_update(
        BoardUpdatePayload(board_id=board_id, name=body.name, columns=body.columns),
        user=require_context().user,
        container=container,
    )
