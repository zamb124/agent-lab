"""Таблица durable execution."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class WorkflowSnapshot(PlatformModel):
    """Якорь проекции. Таблица ``workflow_snapshots``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "workflow_snapshots"
        unique_together: list[tuple[str, str, str, str]] = [
            ("company_id", "session_id", "execution_branch_id", "sequence"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "session_id", "sequence"]),
            Index(["execution_branch_id", "sequence"]),
        ]

    snapshot_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    session_id: str = DbField()
    execution_branch_id: str = DbField()
    sequence: int = DbField(ge=0)
    state_json: JsonObject = DbField(db_type="JSONB")
    state_hash: str = DbField()
    created_at: datetime = DbField()
    schema_version: int = DbField(default=1)
