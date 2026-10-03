"""Таблица проекции A2A."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class A2AArtifactProjection(PlatformModel):
    """Материализованный Artifact. Таблица ``a2a_artifact_projections``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_artifact_projections"
        unique_together: list[tuple[str, str]] = [
            ("task_id", "artifact_id"),
            ("task_id", "ordinal"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "task_id"]),
        ]

    artifact_projection_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    task_id: str = DbField()
    artifact_id: str = DbField()
    ordinal: int = DbField(ge=0)
    artifact_json: JsonObject = DbField(db_type="JSONB")
    latest_sequence: int = DbField(ge=0)
    payload_hash: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    revision: int = DbField(default=1, ge=1)
    is_closed: bool = DbField(default=False)
