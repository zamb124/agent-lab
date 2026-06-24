"""REST API досок задач (зеркало WS-команд worktracker/board/*)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.worktracker.api._common import current_company_id
from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.models.api import BoardCreateRequest, BoardUpdateRequest
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
    items = await container.work_item_service.list_boards(
        current_company_id(), namespace=namespace
    )
    total = len(items)
    page_items = items[offset : offset + limit]
    return OffsetPage[Board](items=page_items, total=total, limit=limit, offset=offset)


@router.get("/{board_id}", response_model=Board)
async def get_board(container: ContainerDep, board_id: str) -> Board:
    try:
        return await container.work_item_service.get_board(current_company_id(), board_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=Board, status_code=201)
async def create_board(container: ContainerDep, body: BoardCreateRequest) -> Board:
    return await container.work_item_service.create_board(
        company_id=current_company_id(),
        name=body.name,
        columns=body.columns,
        namespace=body.namespace,
        board_key=body.board_key,
    )


@router.patch("/{board_id}", response_model=Board)
async def update_board(
    container: ContainerDep, board_id: str, body: BoardUpdateRequest
) -> Board:
    try:
        return await container.work_item_service.update_board(
            company_id=current_company_id(),
            board_id=board_id,
            name=body.name,
            columns=body.columns,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
