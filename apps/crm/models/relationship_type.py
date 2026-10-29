"""Тип связи CRM. В базе ключ — ``relationship_type_row_id``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.queries.select import Query
from pydantic import model_validator

from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage


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
    def row_id_by_company_and_type(cls, company_id: str, type_id: str) -> str:
        """Ключ из company_id и type_id. Пустой company_id или type_id — ValueError."""
        if company_id == "" or type_id == "":
            raise ValueError("relationship type row requires company_id and type_id")
        return f"{len(company_id)}:{company_id}:{type_id}"

    @model_validator(mode="after")
    def bind_row_id(self) -> Self:
        expected = type(self).row_id_by_company_and_type(self.company_id, self.type_id)
        if self.relationship_type_row_id == "":
            self.relationship_type_row_id = expected
        elif self.relationship_type_row_id != expected:
            raise ValueError("relationship_type_row_id does not match company_id and type_id")
        return self

    @classmethod
    def query_by_system_in_company(
        cls,
        company_id: str,
        *,
        include_system: bool,
    ) -> Query[Self]:
        """Запрос типов связи компании. include_system=False оставляет только несистемные. Порядка нет."""
        rows = cls.objects.filter(company_id=company_id)
        if not include_system:
            return rows.filter(is_system=False)
        return rows

    @classmethod
    async def list_by_type_id_asc(cls, company_id: str, *, include_system: bool) -> list[Self]:
        """Типы связи компании, ORDER BY type_id ASC. Предела нет. include_system=False оставляет только несистемные."""
        return await (
            cls.query_by_system_in_company(company_id, include_system=include_system)
            .order_by("type_id")
            .all()
        )

    @classmethod
    async def page_by_type_id_asc(
        cls,
        company_id: str,
        *,
        include_system: bool,
        limit: int,
        offset: int,
    ) -> OffsetPage[Self]:
        """Страница типов связи компании, ORDER BY type_id ASC. include_system=False оставляет только несистемные. limit и offset в теле не проверяются."""
        rows = cls.query_by_system_in_company(company_id, include_system=include_system)
        total = await rows.count()
        types = await rows.order_by("type_id").limit(limit).offset(offset).all()
        return OffsetPage[cls](items=types, total=total, limit=limit, offset=offset)

    @classmethod
    async def list_unordered_with_prompt(cls, company_id: str) -> list[Self]:
        """Типы связей компании, у которых prompt не NULL. Пустая строка входит. Порядка и limit нет."""
        return await cls.objects.filter(
            company_id=company_id,
            prompt__isnull=False,
        ).all()

    @classmethod
    async def update_loaded_by_company_and_type_id(cls, row: Self) -> int:
        """Пишет name, description, prompt, is_directed, inverse_type_id, icon, color, is_system и weight_default строки с тем же company_id и type_id. Возвращает число строк. Нет строки — 0."""
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
