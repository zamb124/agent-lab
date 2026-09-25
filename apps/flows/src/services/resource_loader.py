"""
ResourceLoader - универсальный загрузчик ресурсов.

Заменяет FlowFactory, ToolFactory, NodeFactory.
Единая точка входа для всех ресурсов через Registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.flows.src.models import FlowConfig, NodeConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.runtime.nodes import NodeConstructor
from apps.flows.src.services.flow_factory import FlowFactory
from core.errors import ResourceNotFoundError
from core.logging import get_logger
from core.types import parse_json_object
from core.urn import extract_resource_id

if TYPE_CHECKING:
    from apps.flows.src.registry.nodes import NodeRegistry
    from apps.flows.src.runtime.nodes import BaseNode
    from apps.flows.src.tools.base import BaseTool
    from apps.flows.src.tools.registry import ToolRegistry

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

    node_registry: NodeRegistry
    tool_registry: ToolRegistry
    node_constructor: NodeConstructor
    flow_factory: FlowFactory

    def __init__(
        self,
        node_registry: NodeRegistry,
        tool_registry: ToolRegistry,
        node_constructor: NodeConstructor,
        flow_factory: FlowFactory,
    ) -> None:
        self.node_registry = node_registry
        self.tool_registry = tool_registry
        self.node_constructor = node_constructor
        self.flow_factory = flow_factory

    async def load_flow(self, flow_id: str) -> FlowConfig:
        """
        Загружает FlowConfig из БД.

        Аргументы:
            flow_id: ID flow или URN

        Возвращает:
            FlowConfig

        Исключения:
            ResourceNotFoundError: если flow не найден
        """
        resolved_flow_id = extract_resource_id(flow_id)
        config = await FlowConfig.get_latest(resolved_flow_id)

        if not config:
            raise ResourceNotFoundError(
                resource_type="Flow",
                resource_id=flow_id,
            )

        return config

    async def load_node(self, node_id: str) -> BaseNode:
        """
        Загружает и инстанцирует ноду.

        Аргументы:
            node_id: ID ноды или URN

        Возвращает:
            BaseNode экземпляр

        Исключения:
            ResourceNotFoundError: Если нода не найдена
        """
        resolved_node_id = extract_resource_id(node_id)
        config = await NodeConfig.get(NodeConfig.row_id(resolved_node_id))

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

        Аргументы:
            tool_id: ID tool или URN

        Возвращает:
            BaseTool экземпляр

        Исключения:
            ResourceNotFoundError: Если tool не найден
        """
        resolved_tool_id = extract_resource_id(tool_id)

        config = await ToolReference.get(ToolReference.row_id(resolved_tool_id))
        if not config:
            raise ResourceNotFoundError(
                resource_type="Tool",
                resource_id=tool_id,
            )

        return await self.tool_registry.create_tool(config)

    async def _instantiate_node(self, node_class: type[BaseNode], config: NodeConfig) -> BaseNode:
        """
        Создаёт экземпляр ноды из класса и конфига.

        Аргументы:
            node_class: Класс ноды (из Registry)
            config: NodeConfig из БД

        Возвращает:
            BaseNode экземпляр
        """
        node_config = parse_json_object(config.model_dump_json(), "NodeConfig")
        return node_class.from_config(
            config.node_id,
            node_config,
            node_constructor=self.node_constructor,
            tool_registry=self.tool_registry,
            flow_factory=self.flow_factory,
        )


__all__ = ["ResourceLoader"]
