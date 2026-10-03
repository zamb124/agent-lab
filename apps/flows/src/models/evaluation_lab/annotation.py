"""Таблица evaluation lab: annotation.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationAnnotationType,
)
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationAnnotation(CompanyScopedModel):
    """Заметка к прогону evaluation. Таблица ``evaluation_annotations``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_annotations"
        indexes: list[Index] = [
            Index(["company_id", "run_id"]),
            Index(["company_id", "case_run_id"]),
        ]

    annotation_id: str = DbField(db_pk=True)
    run_id: str = DbField(db_index=True)
    annotation_type: EvaluationAnnotationType = DbField()
    created_by: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    case_run_id: str | None = DbField(default=None)
    case_id: str | None = DbField(default=None)
    comment: str = DbField(default="")
    payload: JsonObject = DbField(default_factory=dict, db_type="JSONB")

    @classmethod
    async def list_for_run(cls, run_id: str) -> list[Self]:
        if run_id == "":
            raise ValueError("run_id is required")
        return await (
            cls.objects.filter(run_id=run_id)
            .order_by("created_at", "annotation_id")
            .all()
        )
