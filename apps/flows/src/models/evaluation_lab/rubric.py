"""Таблица evaluation lab: rubric.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic

from apps.flows.src.models.evaluation_lab.rubric_version import (
    EvaluationRubricVersion,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel


class EvaluationRubric(CompanyScopedModel):
    """Метаданные LLM-судьи. Таблица ``evaluation_rubrics``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_rubrics"
        unique_together: list[tuple[str, str, str]] = [("company_id", "flow_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "flow_id"]),
        ]

    rubric_id: str = DbField(db_pk=True)
    flow_id: str = DbField()
    name: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    archived_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_for_flow(cls, flow_id: str) -> list[Self]:
        if flow_id == "":
            raise ValueError("flow_id is required")
        return await cls.objects.filter(flow_id=flow_id).order_by("-updated_at", "rubric_id").all()

    @classmethod
    async def create_with_first_version(
        cls,
        rubric: Self,
        version: EvaluationRubricVersion,
    ) -> None:
        async with atomic(using="flows"):
            _ = await cls.set(rubric)
            _ = await EvaluationRubricVersion.set(version)

class EvaluationRubricWithVersion(StrictBaseModel):
    rubric: EvaluationRubric
    version: EvaluationRubricVersion
