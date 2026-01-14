"""
Репозиторий для AgentConfig с версионированием.

Хранилище разделено на две таблицы:
- agents: актуальные конфиги агентов (маленькая таблица, по 1 записи на агента)
- agents_versions: история версий (большая таблица, много записей)
"""

import json
from datetime import datetime, timezone
from typing import List, Optional

from apps.agents.src.models import AgentConfig

from core.db import BaseRepository
from core.db import Storage
from core.logging import get_logger

logger = get_logger(__name__)


class AgentRepository(BaseRepository[AgentConfig]):
    """
    Репозиторий для работы с агентами с версионированием.
    Агенты изолированы по компаниям (is_global=False).
    """
    
    is_global = False
    owner_service = "agents"

    def __init__(self, storage: Storage):
        super().__init__(storage, AgentConfig)

    def _get_key(self, entity_id: str) -> str:
        return f"agent:{entity_id}"
    
    def _get_prefix(self) -> str:
        return "agent:"
    
    def _get_table_name(self) -> str:
        return "agents"

    def _get_versions_table(self) -> str:
        return "agents_versions"

    def _extract_entity_id(self, entity: AgentConfig) -> str:
        return entity.agent_id

    async def set(self, entity: AgentConfig) -> bool:
        """
        Сохраняет новую версию агента.
        
        Генерирует timestamp версию и сохраняет:
        - Версию в agents_versions
        - Актуальный конфиг в agents
        """
        agent_id = entity.agent_id
        
        # Генерируем timestamp версию
        new_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        entity.version = new_version
        
        data = entity.model_dump_json()
        
        # Сохраняем версию в agents_versions
        version_key = self._get_key(f"{agent_id}_v{new_version}")
        final_version_key = self._build_final_key(version_key)
        await self._storage._set_with_table(final_version_key, data, self._get_versions_table())
        
        # Сохраняем актуальный конфиг в agents (используем базовый метод)
        await super().set(entity)
        
        logger.info(f"Agent '{agent_id}' saved as version {new_version}")
        return True

    async def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Получает последнюю версию агента."""
        return await self.get_latest(agent_id)

    async def get_latest(self, agent_id: str) -> Optional[AgentConfig]:
        """
        Получает последнюю версию агента из таблицы agents.
        """
        # Используем базовый метод get из BaseRepository
        return await super().get(agent_id)

    async def get_version(self, agent_id: str, version: str) -> Optional[AgentConfig]:
        """
        Получает конкретную версию агента из agents_versions.
        """
        version_key = self._get_key(f"{agent_id}_v{version}")
        final_version_key = self._build_final_key(version_key)
        data = await self._storage._get_with_session_and_table(final_version_key, self._get_versions_table())
        
        if not data:
            return None
            
        return self.model_class.model_validate_json(data)

    async def list_versions(self, agent_id: str) -> List[str]:
        """
        Список всех версий агента (от новых к старым) из agents_versions.
        """
        prefix = self._get_key(f"{agent_id}_v")
        final_prefix = self._build_final_key(prefix)
        all_data = await self._storage._get_all_by_prefix_and_table(final_prefix, self._get_versions_table(), 1000)
        
        versions = []
        for key in all_data.keys():
            # Формат: agent:{agent_id}_v{timestamp} или company:{company_id}:agent:{agent_id}_v{timestamp}
            # Ищем последнее вхождение _v чтобы извлечь timestamp
            parts = key.rsplit("_v", 1)
            if len(parts) == 2:
                versions.append(parts[1])
        
        return sorted(versions, reverse=True)

    async def list_all(self, limit: int = 100) -> List[AgentConfig]:
        """
        Список всех агентов (последние версии).
        
        Читает напрямую из таблицы agents (маленькая таблица с актуальными конфигами).
        """
        # Получаем все ключи из agents (не agents_versions!)
        base_prefix = self._get_prefix()  # "agent:"
        final_prefix = self._build_final_key(base_prefix)
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_prefix, self._get_table_name(), limit
        )
        
        # Парсим каждый агент
        agents = []
        for key, value in all_data.items():
            try:
                agent = self.model_class.model_validate_json(value)
                agents.append(agent)
            except Exception as e:
                logger.warning(f"Failed to parse agent from key {key}: {e}")
                continue
        
        return agents

    async def delete(self, agent_id: str) -> bool:
        """
        Удаляет агента со всеми версиями из обеих таблиц.
        Возвращает False если агент не существовал.
        """
        # Проверяем существование агента через базовый метод get
        agent = await self.get(agent_id)
        
        versions = await self.list_versions(agent_id)
        
        if not agent and not versions:
            logger.info(f"Agent '{agent_id}' not found, nothing to delete")
            return False
        
        # Удаляем актуальный конфиг из agents
        if agent:
            agent_key = self._get_key(agent_id)
            final_agent_key = self._build_final_key(agent_key)
            await self._storage._delete_with_table(final_agent_key, self._get_table_name())
        
        # Удаляем все версии из agents_versions
        for version in versions:
            version_key = self._get_key(f"{agent_id}_v{version}")
            final_version_key = self._build_final_key(version_key)
            await self._storage._delete_with_table(final_version_key, self._get_versions_table())
        
        logger.info(f"Agent '{agent_id}' deleted with {len(versions)} versions")
        return True

    async def rollback_to_version(self, agent_id: str, version: str) -> bool:
        """
        Откатывает агента к указанной версию.
        
        Копирует указанную версию из agents_versions в agents (не удаляет новые версии, не создает новую версию).
        """
        agent = await self.get_version(agent_id, version)
        if agent is None:
            return False
        
        # Копируем версию в agents БЕЗ создания новой версии (используем базовый метод напрямую)
        data = agent.model_dump_json()
        key = self._get_key(agent_id)
        final_key = self._build_final_key(key)
        await self._storage._set_with_table(final_key, data, self._get_table_name())
        
        logger.info(f"Agent '{agent_id}' rolled back to version {version}")
        return True
