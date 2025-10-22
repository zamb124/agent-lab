"""
Репозиторий для работы с AgentConfig.
Наследуется от Storage, поэтому имеет все его методы + типизированную работу с AgentConfig.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentRepository(BaseRepository[AgentConfig]):
    """
    Репозиторий для работы с конфигурациями агентов.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с AgentConfig через Generic[AgentConfig].
    """

    def __init__(self, storage: Storage = None):
        # Передаем model_class=AgentConfig для типизации
        super().__init__(model_class=AgentConfig, storage=storage)

    def _get_key(self, agent_id: str) -> str:
        """Формирует ключ agent:agent_id"""
        return f"agent:{agent_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска агентов"""
        return "agent:"

    async def get(self, agent_id: str) -> Optional[AgentConfig]:
        """
        Получает агента по ID с типизацией.

        Args:
            agent_id: Идентификатор агента

        Returns:
            AgentConfig или None если не найден
        """
        return await self._get_typed(agent_id)

    async def set(self, config: AgentConfig) -> bool:
        """
        Сохраняет конфигурацию агента с типизацией.

        Args:
            config: Конфигурация агента

        Returns:
            True если сохранение успешно
        """
        # Обновляем timestamp
        now = datetime.now(timezone.utc)
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        return await self._set_typed(config)

    async def delete(self, agent_id: str) -> bool:
        """
        Удаляет агента по ID.

        Args:
            agent_id: Идентификатор агента

        Returns:
            True если удаление успешно
        """
        return await self._delete_typed(agent_id)

    async def list_all(self, limit: int = 100) -> List[AgentConfig]:
        """
        Возвращает список всех агентов (оптимизировано).

        Args:
            limit: Максимальное количество результатов

        Returns:
            Список конфигураций агентов
        """
        return await self.list_all_typed(limit=limit)

