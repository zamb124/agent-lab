"""
Репозиторий для работы с Company.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

from typing import List

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import Company

logger = get_logger(__name__)
class CompanyRepository(BaseRepository[Company]):
    """
    Репозиторий для работы с компаниями.
    is_global=True - компании не изолированы (это метаданные самих компаний).
    """

    is_global = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Company)

    def _get_key(self, company_id: str) -> str:
        return f"company:{company_id}"

    def _get_prefix(self) -> str:
        return "company:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: Company) -> str:
        return entity.company_id

    async def list(self, *, limit: int, offset: int = 0) -> List[Company]:
        """
        Возвращает только сущности Company из shared storage.

        В таблице `storage` соседствуют ключи других репозиториев
        (`company:<id>:embed_config:...`, и т.д.), поэтому фильтруем
        только ключи каноничного формата `company:<company_id>`.
        """
        prefix = self._get_prefix()
        table_name = self._get_table_name()
        all_data = await self._storage.get_all_by_prefix_and_table(prefix, table_name, limit, offset)

        entities: List[Company] = []
        for key, data in all_data.items():
            # Company key must have exactly one colon: "company:<id>"
            if key.count(":") != 1:
                continue
            try:
                entity = self.model_class.model_validate_json(data)
                entities.append(entity)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue
        return entities
