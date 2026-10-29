"""Таблица evaluation lab: suite_version.py."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class EvaluationSuiteVersion(CompanyScopedModel):
    """Неизменяемый снимок набора и кейсов. Таблица ``evaluation_suite_versions``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "evaluation_suite_versions"
        unique_together: list[tuple[str, str, str]] = [("company_id", "suite_id", "version")]
        indexes: list[Index] = [
            Index(["company_id", "suite_id"]),
        ]

    suite_version_id: str = DbField(db_pk=True)
    suite_id: str = DbField()
    flow_id: str = DbField()
    flow_config_version: str = DbField()
    version: int = DbField()
    suite_snapshot: JsonObject = DbField(db_type="JSONB")
    cases_snapshot: list[JsonObject] = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    company_id: str = DbField(default="", db_index=True)

    @classmethod
    async def next_after_latest_version_desc(cls, suite_id: str) -> int:
        """Следующий version: последняя строка ORDER BY version DESC, плюс 1. Нет строк — 1. Пустой suite_id — ValueError."""
        if suite_id == "":
            raise ValueError("suite_id is required")
        latest = await cls.objects.filter(suite_id=suite_id).order_by("-version").first()
        if latest is None:
            return 1
        return latest.version + 1
