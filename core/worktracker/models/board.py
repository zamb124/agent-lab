"""Таблица worktracker."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import Field

from core.models.platform_model import PlatformModel
from core.worktracker.models.types import (
    WorkItemState,
    WorktrackerModel,
)


class BoardColumn(WorktrackerModel):
    board_column_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    state: WorkItemState
    position: int = Field(..., ge=0)


def build_generic_board_columns() -> list[BoardColumn]:
    return [
        BoardColumn(
            board_column_id="todo",
            label="To do",
            state=WorkItemState.OPEN,
            position=0,
        ),
        BoardColumn(
            board_column_id="in_progress",
            label="In progress",
            state=WorkItemState.IN_PROGRESS,
            position=1,
        ),
        BoardColumn(
            board_column_id="done",
            label="Done",
            state=WorkItemState.DONE,
            position=2,
        ),
    ]


class Board(PlatformModel):
    """Доска. ``columns`` — JSON этой строки."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    board_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    name: str = DbField(max_length=255, min_length=1)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    namespace: str | None = DbField(default=None, max_length=100)
    board_key: str = DbField(
        default="generic",
        max_length=120,
        description="Логический ключ доски: generic | operator | task | task:<subtype>.",
    )
    columns: list[BoardColumn] = DbField(default_factory=list, db_type="JSONB")

    class Meta:
        is_table: bool = True
        table_name: str = "work_boards"
        indexes: list[Index] = [
            Index(["company_id", "namespace"]),
        ]

    @classmethod
    async def get_board(cls, company_id: str, board_id: str) -> Self:
        board = await cls.objects.filter(
            company_id=company_id,
            board_id=board_id,
        ).get_or_none()
        if board is None:
            raise ValueError(f"Board {board_id!r} not found")
        return board

    @classmethod
    async def company_boards(cls, company_id: str, *, namespace: str | None) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if namespace is not None:
            rows = rows.filter(namespace=namespace)
        return await rows.order_by("created_at").all()

    @classmethod
    async def create(cls, board: Self) -> Self:
        return await cls.objects.create(instance=board)

