"""Предложение CRM: дубликат или пропущенная сущность."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.queries.select import Query

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class CRMSuggest(PlatformModel):
    """Строка ``crm_suggests``. Колонка ключа в базе — ``id``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crm_suggests"
        indexes: list[Index] = [
            Index(["company_id", "namespace", "status"]),
        ]

    suggest_id: str = DbField(db_pk=True, db_column="id", max_length=100)
    company_id: str = DbField(max_length=100, db_index=True)
    namespace: str = DbField(max_length=100, db_index=True)
    suggest_type: str = DbField(max_length=32)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    status: str = DbField(default="pending", max_length=32, db_index=True)
    target_entity_ids: list[str] = DbField(default_factory=list, db_type="JSONB")
    payload: JsonObject = DbField(default_factory=dict, db_type="JSONB")

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    def in_company_namespace(cls, company_id: str, namespace: str) -> Query[Self]:
        return cls.objects.filter(company_id=company_id, namespace=namespace)

    @classmethod
    async def mark_status(
        cls,
        suggest: Self,
        status: str,
        updated_at: datetime,
    ) -> int:
        return await cls.objects.filter(
            suggest_id=suggest.suggest_id,
            company_id=suggest.company_id,
            namespace=suggest.namespace,
        ).update(using="crm", status=status, updated_at=updated_at)
