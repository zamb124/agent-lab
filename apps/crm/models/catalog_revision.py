"""Поколение каталога типов сущностей CRM."""

from __future__ import annotations

from typing import ClassVar

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel


class EntityTypeCatalogRevision(PlatformModel):
    """Поколение каталога ``EntityType``. Плюс один в той же транзакции, что запись типа."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "entity_type_catalog_revision"

    company_id: str = DbField(db_pk=True, max_length=100)
    revision: int

    @classmethod
    async def catalog_revision(cls, company_id: str) -> int:
        row = await cls.objects.filter(company_id=company_id).get_or_none()
        if row is None:
            return 0
        return row.revision

    @classmethod
    async def bump_catalog_revision(cls, company_id: str) -> None:
        _ = cls
        _ = await execute_raw(
            "INSERT INTO entity_type_catalog_revision (company_id, revision) VALUES ($1, 1) ON CONFLICT (company_id) DO UPDATE SET revision = entity_type_catalog_revision.revision + 1",
            [company_id],
            using="crm",
        )
