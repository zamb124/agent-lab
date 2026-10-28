"""Таблица evaluation lab: case.py."""

from __future__ import annotations

import json
from datetime import datetime
from typing import ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import SerializationInfo, field_serializer, model_validator

from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationTargetFlow,
    EvaluationTargetNode,
    EvaluationTurn,
    as_utc,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationCase(CompanyScopedModel):
    """Кейс набора evaluation. Таблица ``evaluation_cases``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_cases"
        unique_together: list[tuple[str, str, str]] = [("company_id", "suite_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
            Index(["company_id", "flow_id"]),
        ]

    case_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    name: str = DbField()
    branch_ids: Literal["*"] | list[str] = DbField(db_type="JSONB")
    turns: list[EvaluationTurn] = DbField(min_length=1, db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    target: EvaluationTargetFlow | EvaluationTargetNode = DbField(
        default_factory=lambda: EvaluationTargetFlow(type="flow"),
        db_type="JSONB",
        discriminator="type",
    )
    initial_state: JsonObject | None = DbField(default=None, db_type="JSONB")
    max_turns: int = DbField(default=10, ge=1, le=200)
    timeout_seconds: int = DbField(default=300, ge=1, le=3600)
    enabled: bool = DbField(default=True)
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    sort_order: int = DbField(default=0)

    @field_serializer("branch_ids")
    def serialize_branch_ids(
        self,
        value: Literal["*"] | list[str],
        info: SerializationInfo,
    ) -> str | list[str]:
        # Oxyde кладёт строку в jsonb только если она сама является JSON.
        if info.mode == "python" and isinstance(value, str):
            return json.dumps(value)
        return value

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        self.created_at = as_utc(self.created_at)
        self.updated_at = as_utc(self.updated_at)
        return self

    @classmethod
    async def list_by_sort_order_created_at_and_case_id(cls, suite_id: str) -> list[Self]:
        """Кейсы набора, ORDER BY sort_order, created_at, case_id. Предела нет. Пустой suite_id — ValueError."""
        if suite_id == "":
            raise ValueError("suite_id is required")
        return await (
            cls.objects.filter(suite_id=suite_id)
            .order_by("sort_order", "created_at", "case_id")
            .all()
        )

class EvaluationCaseImportResult(StrictBaseModel):
    cases: list[EvaluationCase]
