"""
Репозиторий для связи tenant (company) и entity в crm_entities.
Работает с SQLAlchemy напрямую.
"""

from typing import override

from sqlalchemy import select

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import CompanyMapping
from core.logging import get_logger

logger = get_logger(__name__)


class CompanyMappingRepository(BaseCRMRepository[CompanyMapping]):
    """
    Репозиторий для связи company (tenant) и entity в crm_entities.

    При первом входе в CRM создается entity типа 'organization'
    для компании пользователя.

    Глобальный - одна запись на company_id.
    """

    def __init__(self, db: CRMDatabase):
        super().__init__(db)

    @property
    @override
    def model_class(self) -> type[CompanyMapping]:
        return CompanyMapping

    @property
    @override
    def id_field(self) -> str:
        return "company_id"

    async def get_by_entity(self, entity_id: str) -> CompanyMapping | None:
        """Получает mapping по entity_id"""
        async with self._db.session() as session:
            stmt = select(CompanyMapping).where(CompanyMapping.entity_id == entity_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
