"""
Репозиторий для работы с ToolReference.
Наследуется от Storage, поэтому имеет все его методы + типизированную работу с ToolReference.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import ToolReference

logger = logging.getLogger(__name__)


class ToolRepository(BaseRepository[ToolReference]):
    """
    Репозиторий для работы с инструментами.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с ToolReference через Generic[ToolReference].
    """

    def __init__(self, storage: Storage = None):
        # Передаем model_class=ToolReference для типизации
        super().__init__(model_class=ToolReference, storage=storage)

    def _get_key(self, tool_id: str) -> str:
        """Формирует ключ tool:tool_id"""
        return f"tool:{tool_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска инструментов"""
        return "tool:"

    async def get(self, tool_id: str) -> Optional[ToolReference]:
        """
        Получает инструмент по ID с типизацией.

        Args:
            tool_id: Идентификатор инструмента

        Returns:
            ToolReference или None если не найден
        """
        return await self._get_typed(tool_id)

    async def set(self, config: ToolReference) -> bool:
        """
        Сохраняет конфигурацию инструмента с типизацией.

        Args:
            config: Конфигурация инструмента

        Returns:
            True если сохранение успешно
        """
        return await self._set_typed(config)

    async def delete(self, tool_id: str) -> bool:
        """
        Удаляет инструмент по ID.

        Args:
            tool_id: Идентификатор инструмента

        Returns:
            True если удаление успешно
        """
        return await self._delete_typed(tool_id)

    async def list_all(self, limit: int = 100) -> List[ToolReference]:
        """
        Возвращает список всех инструментов (оптимизировано).

        Args:
            limit: Максимальное количество результатов

        Returns:
            Список конфигураций инструментов
        """
        return await self.list_all_typed(limit=limit)

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

