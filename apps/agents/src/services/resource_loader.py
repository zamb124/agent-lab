"""
ResourceLoader - универсальный загрузчик ресурсов.

Заменяет AgentFactory, ToolFactory, NodeFactory.
Единая точка входа для всех ресурсов через Registry.
"""

from typing import Optional

from core.errors import ResourceNotFoundError
from core.urn import AgentURN, NodeURN, ToolURN, extract_id
from apps.agents.src.models import AgentConfig, NodeConfig
from apps.agents.src.agent.nodes import BaseNode
from apps.agents.src.tools.base import BaseTool
from apps.agents.src.db import AgentRepository, NodeRepository, ToolRepository
from apps.agents.src.registry.nodes import NodeRegistry
from apps.agents.src.tools.registry import ToolRegistry
from core.logging import get_logger

logger = get_logger(__name__)


class ResourceLoader:
    """
    Универсальный загрузчик ресурсов.
    
    Принципы:
    1. Использует Registry для резолвинга типов
    2. Использует Repository для загрузки из БД
    3. Никаких угадываний - явные ошибки
    4. Поддержка URN и обычных ID
    """
    
    def __init__(
        self,
        node_registry: NodeRegistry,
        tool_registry: ToolRegistry,
        agent_repository: AgentRepository,
        node_repository: NodeRepository,
        tool_repository: ToolRepository,
    ):
        self.node_registry = node_registry
        self.tool_registry = tool_registry
        self.agent_repository = agent_repository
        self.node_repository = node_repository
        self.tool_repository = tool_repository
    
    async def load_agent(self, agent_id: str) -> AgentConfig:
        """
        Загружает конфиг агента из БД.
        
        Args:
            agent_id: ID агента или URN
        
        Returns:
            AgentConfig
        
        Raises:
            ResourceNotFoundError: Если агент не найден
        """
        id_str = extract_id(agent_id)
        config = await self.agent_repository.get(id_str)
        
        if not config:
            raise ResourceNotFoundError(
                resource_type="Agent",
                resource_id=agent_id,
            )
        
        return config
    
    async def load_node(self, node_id: str) -> BaseNode:
        """
        Загружает и инстанцирует ноду.
        
        Args:
            node_id: ID ноды или URN
        
        Returns:
            BaseNode экземпляр
        
        Raises:
            ResourceNotFoundError: Если нода не найдена
        """
        id_str = extract_id(node_id)
        config = await self.node_repository.get(id_str)
        
        if not config:
            raise ResourceNotFoundError(
                resource_type="Node",
                resource_id=node_id,
            )
        
        node_class = self.node_registry.get(config.type)
        return await self._instantiate_node(node_class, config)
    
    async def load_tool(self, tool_id: str) -> BaseTool:
        """
        Загружает tool.
        
        Args:
            tool_id: ID tool или URN
        
        Returns:
            BaseTool экземпляр
        
        Raises:
            ResourceNotFoundError: Если tool не найден
        """
        id_str = extract_id(tool_id)
        
        # Сначала пробуем зарегистрированные tools
        if self.tool_registry.has(id_str):
            return self.tool_registry.get(id_str)
        
        # Затем из БД
        config = await self.tool_repository.get(id_str)
        if not config:
            raise ResourceNotFoundError(
                resource_type="Tool",
                resource_id=tool_id,
            )
        
        # Создаём inline tool из config
        return await self.tool_registry.create_tool({
            "tool_id": config.tool_id,
            "code": config.code,
            "title": config.title,
            "description": config.description,
            "args_schema": config.args_schema,
        })
    
    async def _instantiate_node(self, node_class: type, config: NodeConfig) -> BaseNode:
        """
        Создаёт экземпляр ноды из класса и конфига.
        
        Args:
            node_class: Класс ноды (из Registry)
            config: NodeConfig из БД
        
        Returns:
            BaseNode экземпляр
        """
        return node_class.from_config(config.node_id, config.model_dump())


__all__ = ["ResourceLoader"]
