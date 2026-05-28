"""
Репозиторий для работы с маппингом subdomain → company_id.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

from typing import ClassVar, override

from pydantic import BaseModel

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger

logger = get_logger(__name__)


class SubdomainMapping(BaseModel):
    """Модель для маппинга subdomain → company_id"""

    subdomain: str
    company_id: str


class SubdomainRepository(BaseRepository[SubdomainMapping]):
    """
    Репозиторий для маппинга subdomain → company_id.
    is_global=True - маппинги не изолированы по компаниям.
    """

    is_global: ClassVar[bool] = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=SubdomainMapping)

    @override
    def _get_key(self, subdomain: str) -> str:
        return f"subdomain:{subdomain}"

    @override
    def _get_prefix(self) -> str:
        return "subdomain:"

    @override
    def _get_table_name(self) -> str:
        return "storage"

    @override
    def _extract_entity_id(self, entity: SubdomainMapping) -> str:
        return entity.subdomain

    async def get_company_id(self, subdomain: str) -> str | None:
        """
        Получает company_id по subdomain.

        Аргументы:
            subdomain: Поддомен

        Возвращает:
            company_id или None
        """
        mapping = await self.get(subdomain)
        return mapping.company_id if mapping else None

    async def set_mapping(self, subdomain: str, company_id: str) -> bool:
        """
        Устанавливает маппинг subdomain → company_id.

        Аргументы:
            subdomain: Поддомен
            company_id: ID компании

        Возвращает:
            True если сохранение успешно
        """
        mapping = SubdomainMapping(subdomain=subdomain, company_id=company_id)
        return await self.set(mapping)
