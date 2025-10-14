"""
Репозиторий для работы с ToolReference.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import ToolReference

logger = logging.getLogger(__name__)


class ToolRepository(BaseRepository[ToolReference]):
    """Репозиторий для работы с инструментами"""

    def _get_key(self, tool_id: str) -> str:
        """Формирует ключ tool:tool_id"""
        return f"tool:{tool_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска инструментов"""
        return "tool:"

    async def get(self, tool_id: str) -> Optional[ToolReference]:
        """
        Получает инструмент по ID.
        
        Args:
            tool_id: Идентификатор инструмента
            
        Returns:
            ToolReference или None если не найден
        """
        key = self._get_key(tool_id)
        data = await self.storage.get(key)
        if data:
            try:
                return ToolReference.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга инструмента {tool_id}: {e}")
                return None
        return None

    async def set(self, config: ToolReference) -> bool:
        """
        Сохраняет конфигурацию инструмента.
        
        Args:
            config: Конфигурация инструмента
            
        Returns:
            True если сохранение успешно
        """
        key = self._get_key(config.tool_id)
        data = config.model_dump_json()
        return await self.storage.set(key, data)

    async def delete(self, tool_id: str) -> bool:
        """
        Удаляет инструмент по ID.
        
        Args:
            tool_id: Идентификатор инструмента
            
        Returns:
            True если удаление успешно
        """
        key = self._get_key(tool_id)
        return await self.storage.delete(key)

    async def list_all(self, limit: int = 100) -> List[ToolReference]:
        """
        Возвращает список всех инструментов.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список конфигураций инструментов
        """
        prefix = self._get_prefix()
        keys = await self.storage.list_by_prefix(prefix, limit=limit)
        
        tools = []
        for key in keys:
            data = await self.storage.get(key)
            if data:
                try:
                    tool = ToolReference.model_validate_json(data)
                    tools.append(tool)
                except Exception as e:
                    logger.error(f"Ошибка парсинга инструмента {key}: {e}")
                    continue
        
        return tools

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

