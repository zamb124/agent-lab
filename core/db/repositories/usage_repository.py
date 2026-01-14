"""
Репозиторий для работы с UsageRecord.
Использует shared БД, is_global=False (изолирован по компаниям).
Хранит данные в отдельной таблице usage.
"""

import logging
from typing import List

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.billing_models import UsageRecord

logger = logging.getLogger(__name__)


class UsageRepository(BaseRepository[UsageRecord]):
    """
    Репозиторий для работы с записями использования.
    is_global=False - записи изолированы по компаниям.
    Хранит данные в таблице usage в shared_db.
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=UsageRecord)

    def _get_key(self, usage_id: str) -> str:
        return f"usage:{usage_id}"

    def _get_key_with_resource(self, resource_name: str, usage_id: str) -> str:
        return f"usage:{resource_name}:{usage_id}"

    def _get_prefix(self) -> str:
        return "usage:"

    def _get_table_name(self) -> str:
        return "usage"

    def _extract_entity_id(self, entity: UsageRecord) -> str:
        return entity.usage_id
    
    async def set(self, entity: UsageRecord) -> bool:
        """Сохраняет запись с resource_name в ключе"""
        base_key = self._get_key_with_resource(entity.resource_name, entity.usage_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        data = entity.model_dump_json()
        return await self._storage._set_with_table(final_key, data, table_name)

    async def list_by_company(self, limit: int = 10000) -> List[UsageRecord]:
        """
        Получает все записи использования для текущей компании.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список записей использования
        """
        return await self.list_all(limit=limit)

