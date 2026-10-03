"""Таблица evaluation lab: suite.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import model_validator

from apps.flows.src.models.evaluation_lab.contracts import (
    as_utc,
)
from core.models.platform_model import CompanyScopedModel


class EvaluationSuite(CompanyScopedModel):
    """Набор кейсов evaluation. Таблица ``evaluation_suites``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_suites"
        unique_together: list[tuple[str, str, str]] = [("company_id", "flow_id", "name")]
        indexes: list[Index] = [
            Index(["company_id", "flow_id"]),
        ]

    suite_id: str = DbField(db_pk=True)
    flow_id: str = DbField()
    name: str = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)
    description: str = DbField(default="")
    tags: list[str] = DbField(default_factory=list, db_type="JSONB")
    archived_at: datetime | None = DbField(default=None)

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        self.created_at = as_utc(self.created_at)
        self.updated_at = as_utc(self.updated_at)
        if self.archived_at is not None:
            self.archived_at = as_utc(self.archived_at)
        return self

    @classmethod
    async def list_for_flow(cls, flow_id: str) -> list[Self]:
        if flow_id == "":
            raise ValueError("flow_id is required")
        return await cls.objects.filter(flow_id=flow_id).order_by("-updated_at", "suite_id").all()
