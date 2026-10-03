"""Таблица durable execution."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.durable_execution.models.contracts import (
    ExecutionBranchReason,
)
from core.models.platform_model import PlatformModel


class ExecutionBranch(PlatformModel):
    """Линия fork/rewind/retry. Таблица ``execution_branches``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "execution_branches"
        indexes: list[Index] = [
            Index(["company_id", "session_id"]),
            Index(["parent_execution_branch_id"]),
        ]

    execution_branch_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    reason: ExecutionBranchReason = DbField()
    created_at: datetime = DbField()
    base_sequence: int = DbField(default=0, ge=0)
    parent_execution_branch_id: str | None = DbField(default=None)
    base_state_hash: str | None = DbField(default=None)
