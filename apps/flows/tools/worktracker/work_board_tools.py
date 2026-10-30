"""Builtin tools Board / columns для flow-employee / Lara."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.worktracker_client import WorktrackerClient
from core.context import require_active_company
from core.models import StrictBaseModel
from core.types import JsonObject
from core.worktracker.models import Board, BoardColumn, WorkItemState, build_generic_board_columns

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState

_TAGS = ["worktracker"]


class BoardColumnInput(StrictBaseModel):
    board_column_id: str = Field(..., min_length=1, description="Стабильный id колонки.")
    label: str = Field(..., min_length=1, description="Подпись колонки.")
    item_state: str = Field(
        ...,
        description="WorkItemState колонки: open|in_progress|blocked|done|cancelled|failed.",
    )
    position: int = Field(..., ge=0, description="Порядок колонки слева направо (0-based).")


class WorkBoardListArgs(StrictBaseModel):
    namespace: str | None = Field(
        default=None,
        description="Фильтр namespace. Omit/null — все / ensure generic.",
    )


class WorkBoardGetArgs(StrictBaseModel):
    board_id: str = Field(..., min_length=1, description="board_id из list/create.")


class WorkBoardCreateArgs(StrictBaseModel):
    name: str = Field(..., min_length=1, description="Имя доски.")
    namespace: str | None = Field(
        default=None,
        description="Namespace доски. Omit/null — company default.",
    )
    board_key: str = Field(
        default="generic",
        description="Логический ключ: generic | operator | task | task:<subtype>.",
    )
    columns: list[BoardColumnInput] = Field(
        default_factory=list,
        description="Колонки. Пустой список — стандартные To do / In progress / Done.",
    )


class WorkBoardUpdateArgs(StrictBaseModel):
    board_id: str = Field(..., min_length=1, description="board_id для update.")
    name: str | None = Field(default=None, description="Новое имя. Omit — не менять.")
    columns: list[BoardColumnInput] | None = Field(
        default=None,
        description="Полная замена колонок. Omit — не менять.",
    )


def _board_payload(board: Board) -> JsonObject:
    return {
        "board_id": board.board_id,
        "name": board.name,
        "namespace": board.namespace,
        "board_key": board.board_key,
        "columns": [
            {
                "board_column_id": col.board_column_id,
                "label": col.label,
                "item_state": col.state.value,
                "position": col.position,
            }
            for col in board.columns
        ],
    }


def _columns_from_input(columns: list[BoardColumnInput]) -> list[BoardColumn]:
    if not columns:
        return build_generic_board_columns()
    return [
        BoardColumn(
            board_column_id=col.board_column_id,
            label=col.label,
            state=WorkItemState(col.item_state),
            position=col.position,
        )
        for col in columns
    ]


@tool(
    name="work_board_list",
    description=(
        "Lists WorkItem boards for the company (ensures generic board if empty). "
        "Use before work_item_move to learn board_id / board_column_id. "
        "Returns items[] with board_id, name, board_key, columns."
    ),
    tags=_TAGS,
    parameters_model=WorkBoardListArgs,
)
async def work_board_list(
    namespace: str | None = None,
    *,
    state: "ExecutionState",
    worktracker_client: WorktrackerClient,
) -> JsonObject:
    _ = state
    args = WorkBoardListArgs(namespace=namespace)
    boards = await worktracker_client.list_boards(
        require_active_company().company_id,
        namespace=args.namespace,
    )
    return {"items": [_board_payload(board) for board in boards]}


@tool(
    name="work_board_get",
    description=(
        "Loads one board by board_id including columns (board_column_id, label, item_state). "
        "Call before move to pick the target column. Never invent board_id."
    ),
    tags=_TAGS,
    parameters_model=WorkBoardGetArgs,
)
async def work_board_get(
    board_id: str,
    *,
    state: "ExecutionState",
    worktracker_client: WorktrackerClient,
) -> JsonObject:
    _ = state
    args = WorkBoardGetArgs(board_id=board_id)
    board = await worktracker_client.get_board(
        require_active_company().company_id,
        args.board_id,
    )
    return _board_payload(board)


@tool(
    name="work_board_create",
    description=(
        "Creates a board with optional columns (default To do / In progress / Done). "
        "Returns board_id and columns. Use work_item_move with board_column_id afterwards."
    ),
    tags=_TAGS,
    parameters_model=WorkBoardCreateArgs,
)
async def work_board_create(
    name: str,
    namespace: str | None = None,
    board_key: str = "generic",
    columns: list[BoardColumnInput] | None = None,
    *,
    state: "ExecutionState",
    worktracker_client: WorktrackerClient,
) -> JsonObject:
    _ = state
    args = WorkBoardCreateArgs(
        name=name,
        namespace=namespace,
        board_key=board_key,
        columns=columns if columns is not None else [],
    )
    board = await worktracker_client.create_board(
        company_id=require_active_company().company_id,
        name=args.name,
        columns=_columns_from_input(args.columns),
        namespace=args.namespace,
        board_key=args.board_key,
    )
    return _board_payload(board)


@tool(
    name="work_board_update",
    description=(
        "Updates board name and/or replaces columns entirely. "
        "Omit fields you do not change. Returns updated board payload."
    ),
    tags=_TAGS,
    parameters_model=WorkBoardUpdateArgs,
)
async def work_board_update(
    board_id: str,
    name: str | None = None,
    columns: list[BoardColumnInput] | None = None,
    *,
    state: "ExecutionState",
    worktracker_client: WorktrackerClient,
) -> JsonObject:
    _ = state
    args = WorkBoardUpdateArgs(board_id=board_id, name=name, columns=columns)
    resolved_columns = (
        _columns_from_input(args.columns) if args.columns is not None else None
    )
    board = await worktracker_client.update_board(
        company_id=require_active_company().company_id,
        board_id=args.board_id,
        name=args.name,
        columns=resolved_columns,
    )
    return _board_payload(board)
