"""
ResourceLoader - универсальный загрузчик ресурсов.

Заменяет FlowFactory, ToolFactory, NodeFactory.
Единая точка входа для всех ресурсов через Registry.
"""


from apps.flows.src.db import FlowRepository, NodeRepository, ToolRepository
from apps.flows.src.models import FlowConfig, NodeConfig
from apps.flows.src.registry.nodes import NodeRegistry
from apps.flows.src.runtime.nodes import BaseNode
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.registry import ToolRegistry
from core.errors import ResourceNotFoundError
from core.logging import get_logger
from core.urn import extract_id

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
        flow_repository: FlowRepository,
        node_repository: NodeRepository,
        tool_repository: ToolRepository,
    ):
        self.node_registry = node_registry
        self.tool_registry = tool_registry
        self.flow_repository = flow_repository
        self.node_repository = node_repository
        self.tool_repository = tool_repository

    async def load_flow(self, flow_id: str) -> FlowConfig:
        """
        Загружает FlowConfig из БД.

        Args:
            flow_id: ID flow или URN

        Returns:
            FlowConfig

        Raises:
            ResourceNotFoundError: если flow не найден
        """
        id_str = extract_id(flow_id)
        config = await self.flow_repository.get(id_str)

        if not config:
            raise ResourceNotFoundError(
                resource_type="Flow",
                resource_id=flow_id,
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
