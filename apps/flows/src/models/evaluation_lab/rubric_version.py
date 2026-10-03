"""Таблица evaluation lab: rubric_version.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import CompanyScopedModel


class EvaluationRubricVersion(CompanyScopedModel):
    """Неизменяемый промпт рубрики. Таблица ``evaluation_rubric_versions``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_rubric_versions"
        unique_together: list[tuple[str, str, str]] = [("company_id", "rubric_id", "version")]
        indexes: list[Index] = [
            Index(["company_id", "rubric_id"]),
        ]

    rubric_version_id: str = DbField(db_pk=True)
    rubric_id: str = DbField()
    flow_id: str = DbField()
    version: int = DbField()
    prompt: str = DbField(min_length=1, db_type="TEXT")
    pass_threshold: float = DbField(ge=0.0, le=10.0)
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)

    @classmethod
    async def list_for_rubric(cls, rubric_id: str) -> list[Self]:
        if rubric_id == "":
            raise ValueError("rubric_id is required")
        return await cls.objects.filter(rubric_id=rubric_id).order_by("-version").all()

    @classmethod
    async def next_version(cls, rubric_id: str) -> int:
        if rubric_id == "":
            raise ValueError("rubric_id is required")
        latest = await cls.objects.filter(rubric_id=rubric_id).order_by("-version").first()
        if latest is None:
            return 1
        return latest.version + 1
