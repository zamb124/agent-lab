"""
Репозиторий для работы с ToolReference.
Использует service БД, is_global=False (изолирован по компаниям).
"""

import logging
from typing import Optional, List

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models import ToolReference

logger = logging.getLogger(__name__)


class ToolRepository(BaseRepository[ToolReference]):
    """
    Репозиторий для работы с инструментами.
    is_global=False - инструменты изолированы по компаниям.
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=ToolReference)

    def _get_key(self, tool_id: str) -> str:
        return f"tool:{tool_id}"

    def _get_prefix(self) -> str:
        return "tool:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: ToolReference) -> str:
        return entity.tool_id

    async def list_public(self, limit: int = 100) -> List[ToolReference]:
        """
        Возвращает список всех публичных инструментов.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список публичных инструментов
        """
        all_tools = await self.list_all(limit=limit)
        return [tool for tool in all_tools if getattr(tool, 'is_public', False)]
