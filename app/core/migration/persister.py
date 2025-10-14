"""
ConfigPersister - компонент для сохранения конфигураций в БД.
"""

import logging
from app.db.repositories import Storage, AgentRepository, FlowRepository, ToolRepository
from app.models import AgentConfig, FlowConfig, ToolReference
from app.core.container import get_container

logger = logging.getLogger(__name__)


class ConfigPersister:
    """Сохранение конфигураций в БД через репозитории"""

    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        self.agent_repository = get_container().get_agent_repository()
        self.flow_repository = get_container().get_flow_repository()
        self.tool_repository = get_container().get_tool_repository()

    async def save_agent(self, config: AgentConfig) -> bool:
        """
        Сохраняет конфигурацию агента в БД.
        
        Args:
            config: Конфигурация агента
            
        Returns:
            True если сохранение успешно
        """
        return await self.agent_repository.set(config)

    async def save_flow(self, config: FlowConfig) -> bool:
        """
        Сохраняет конфигурацию flow в БД.
        
        Args:
            config: Конфигурация flow
            
        Returns:
            True если сохранение успешно
        """
        return await self.flow_repository.set(config)

    async def save_tool(self, config: ToolReference) -> bool:
        """
        Сохраняет конфигурацию tool в БД.
        
        Args:
            config: Конфигурация tool
            
        Returns:
            True если сохранение успешно
        """
        return await self.tool_repository.set(config)

