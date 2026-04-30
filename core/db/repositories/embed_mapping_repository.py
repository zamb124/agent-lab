"""
Репозиторий для глобального маппинга embed_id -> company_id.
"""

from core.logging import get_logger
from typing import Optional

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.embed_models import EmbedMapping

logger = get_logger(__name__)
class EmbedMappingRepository(BaseRepository[EmbedMapping]):
    """
    Глобальный маппинг для поиска компании по embed_id.
    is_global=True - маппинг доступен глобально без префикса компании.
    
    Ключи: embed_mapping:{embed_id}
    """
    
    is_global = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=EmbedMapping)

    def _get_key(self, embed_id: str) -> str:
        return f"embed_mapping:{embed_id}"

    def _get_prefix(self) -> str:
        return "embed_mapping:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: EmbedMapping) -> str:
        return entity.embed_id
    
    async def get_company_id(self, embed_id: str) -> Optional[str]:
        """
        Получение company_id по embed_id.
        
        Args:
            embed_id: ID виджета
            
        Returns:
            company_id или None если маппинг не найден
        """
        mapping = await self.get(embed_id)
        if mapping:
            logger.debug(f"Найден маппинг для {embed_id} -> {mapping.company_id}")
            return mapping.company_id
        
        logger.warning(f"Маппинг для {embed_id} не найден")
        return None
    
    async def delete_by_embed_id(self, embed_id: str) -> bool:
        """
        Удаление маппинга по embed_id.
        
        Args:
            embed_id: ID виджета
            
        Returns:
            True если удален, False если не найден
        """
        mapping = await self.get(embed_id)
        if mapping:
            await self.delete(embed_id)
            logger.info(f"Удален маппинг для {embed_id}")
            return True
        return False

