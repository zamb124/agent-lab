"""Тип связи CRM. В базе ключ — ``relationship_type_row_id``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.queries.select import Query
from pydantic import model_validator

from core.models.platform_model import PlatformModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RelationshipType(PlatformModel):
    """Строка ``relationship_types``. Ответ API — эта же модель.

    Один ``type_id`` (``mentions``) живёт в каждой компании своей строкой.
    Первичный ключ — ``relationship_type_row_id``. Пара ``(company_id, type_id)`` уникальна.
    """

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "relationship_types"
        unique_together: list[tuple[str, str]] = [("company_id", "type_id")]
        indexes: list[Index] = [
            Index(["is_system"]),
        ]

    relationship_type_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    type_id: str = DbField(max_length=100, db_index=True)
    company_id: str = DbField(max_length=100, db_index=True)
    name: str = DbField(max_length=200)
    created_at: datetime = DbField(default_factory=_utcnow)
    description: str | None = DbField(default=None, db_type="TEXT")
    prompt: str | None = DbField(default=None, db_type="TEXT")
    is_directed: bool = DbField(default=True)
    inverse_type_id: str | None = DbField(default=None, max_length=100)
    icon: str | None = DbField(default=None, max_length=50)
    color: str | None = DbField(default=None, max_length=20)
    is_system: bool = DbField(default=False)
    weight_default: float = DbField(default=1.0)

    @classmethod
    def row_id(cls, company_id: str, type_id: str) -> str:
        if company_id == "" or type_id == "":
            raise ValueError("relationship type row requires company_id and type_id")
        return f"{len(company_id)}:{company_id}:{type_id}"

    @model_validator(mode="after")
    def bind_row_id(self) -> Self:
        expected = type(self).row_id(self.company_id, self.type_id)
        if self.relationship_type_row_id == "":
            self.relationship_type_row_id = expected
        elif self.relationship_type_row_id != expected:
            raise ValueError("relationship_type_row_id does not match company_id and type_id")
        return self

    @classmethod
    def in_company(
        cls,
        company_id: str,
        *,
        include_system: bool,
    ) -> Query[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if not include_system:
            return rows.filter(is_system=False)
        return rows

    @classmethod
    async def all_with_prompt(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            prompt__isnull=False,
        ).all()

    @classmethod
    async def update_by_company_and_type_id(cls, row: Self) -> int:
        return await cls.objects.filter(
            company_id=row.company_id,
            type_id=row.type_id,
        ).update(
            using="crm",
            name=row.name,
            description=row.description,
            prompt=row.prompt,
            is_directed=row.is_directed,
            inverse_type_id=row.inverse_type_id,
            icon=row.icon,
            color=row.color,
            is_system=row.is_system,
            weight_default=row.weight_default,
        )

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)
