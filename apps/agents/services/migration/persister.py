"""
ConfigPersister - компонент для сохранения конфигураций в БД.
"""

import logging
from apps.agents.models import AgentConfig, FlowConfig, ToolReference
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


class ConfigPersister:
    """Сохранение конфигураций в БД через репозитории"""

    def __init__(self):
        pass

    async def save_agent(self, config: AgentConfig) -> bool:
        """
        Сохраняет конфигурацию агента в БД.
        
        Args:
            config: Конфигурация агента
            
        Returns:
            True если сохранение успешно
        """
        return await get_agents_container().agent_repository.set(config)

    async def save_flow(self, config: FlowConfig) -> bool:
        """
        Сохраняет конфигурацию flow в БД.
        
        Args:
            config: Конфигурация flow
            
        Returns:
            True если сохранение успешно
        """
        return await get_agents_container().flow_repository.set(config)

    async def save_tool(self, config: ToolReference) -> bool:
        """
        Сохраняет конфигурацию tool в БД.
        
        Args:
            config: Конфигурация tool
            
        Returns:
            True если сохранение успешно
        """
        return await get_agents_container().tool_repository.set(config)

