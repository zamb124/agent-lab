"""
Репозиторий для работы с AgentConfig.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentRepository(BaseRepository[AgentConfig]):
    """Репозиторий для работы с конфигурациями агентов"""

    def _get_key(self, agent_id: str) -> str:
        """Формирует ключ agent:agent_id"""
        return f"agent:{agent_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска агентов"""
        return "agent:"

    async def get(self, agent_id: str) -> Optional[AgentConfig]:
        """
        Получает агента по ID.
        
        Args:
            agent_id: Идентификатор агента
            
        Returns:
            AgentConfig или None если не найден
        """
        key = self._get_key(agent_id)
        data = await self.storage.get(key)
        if data is None:
            return None
        return AgentConfig.model_validate_json(data)

    async def set(self, config: AgentConfig) -> bool:
        """
        Сохраняет конфигурацию агента.
        
        Args:
            config: Конфигурация агента
            
        Returns:
            True если сохранение успешно
        """
        now = datetime.now(timezone.utc)
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        key = self._get_key(config.agent_id)
        data = config.model_dump_json()
        return await self.storage.set(key, data)

    async def delete(self, agent_id: str) -> bool:
        """
        Удаляет агента по ID.
        
        Args:
            agent_id: Идентификатор агента
            
        Returns:
            True если удаление успешно
        """
        key = self._get_key(agent_id)
        return await self.storage.delete(key)

    async def list_all(self, limit: int = 100) -> List[AgentConfig]:
        """
        Возвращает список всех агентов.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список конфигураций агентов
        """
        prefix = self._get_prefix()
        keys = await self.storage.list_by_prefix(prefix, limit=limit)
        
        agents = []
        for key in keys:
            data = await self.storage.get(key)
            if data:
                try:
                    agent = AgentConfig.model_validate_json(data)
                    agents.append(agent)
                except Exception as e:
                    logger.error(f"Ошибка парсинга агента {key}: {e}")
                    continue
        
        return agents

