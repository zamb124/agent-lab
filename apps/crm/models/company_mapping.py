"""Связь компании платформы с сущностью CRM."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde.exceptions import UniqueViolationError

from core.logging import get_logger
from core.models.platform_model import PlatformModel

logger = get_logger(__name__)


class CompanyMapping(PlatformModel):
    """Одна строка на компанию. Таблица ``company_mapping``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "company_mapping"

    company_id: str = DbField(db_pk=True, max_length=100)
    entity_id: str = DbField(max_length=100, db_index=True)
    created_at: datetime = DbField()
    is_owner: bool = DbField(default=True)

    @classmethod
    async def for_entity(cls, entity_id: str) -> Self | None:
        return await cls.objects.filter(entity_id=entity_id).get_or_none()

    @classmethod
    async def ensure_for_company(cls, company_id: str, entity_id: str) -> None:
        """Один ``company_mapping`` на компанию. UniqueViolation = параллельный worker уже записал."""
        existing_mapping = await cls.get(company_id)
        if existing_mapping is not None:
            return
        mapping = cls(
            company_id=company_id,
            entity_id=entity_id,
            is_owner=True,
            created_at=datetime.now(UTC),
        )
        try:
            _ = await cls.objects.create(instance=mapping)
        except UniqueViolationError:
            logger.info("crm.companymapping.company.worker", company_id=company_id)
