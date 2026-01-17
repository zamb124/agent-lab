"""
NodeRegistry - реестр типов нод.

Регистрирует и предоставляет классы нод по NodeType.
Zero-Guess: все типы нод регистрируются явно при startup.
"""

from typing import Type, Dict

from core.registry.base import ResourceRegistry
from core.errors import ResourceNotFoundError
from apps.agents.src.models.enums import NodeType
from apps.agents.src.agent.nodes import (
    ReactNode,
    CodeNode,
    AgentNode,
    RemoteAgentNode,
    ExternalAPINode,
    MCPNode,
)


class NodeRegistry(ResourceRegistry):
    """
    Реестр классов нод по типам.
    
    При startup регистрируются все доступные типы нод:
    - NodeType.REACT_NODE → ReactNode
    - NodeType.CODE → CodeNode
    - NodeType.AGENT → AgentNode
    - и т.д.
    
    Zero-Guess: попытка получить незарегистрированный тип = ошибка.
    
    Examples:
        >>> registry = NodeRegistry()
        >>> registry.register(NodeType.REACT_NODE, ReactNode)
        >>> node_class = registry.get(NodeType.REACT_NODE)
    """
    
    def register(self, node_type: NodeType, node_class: Type, metadata: Dict = None) -> None:
        """
        Регистрирует класс ноды.
        
        Args:
            node_type: Тип ноды (NodeType Enum)
            node_class: Класс ноды (наследник BaseNode)
            metadata: Дополнительные метаданные
        
        Raises:
            ResourceAlreadyExistsError: Если тип уже зарегистрирован
        """
        super().register(node_type.value, node_class, metadata)
    
    def get(self, node_type: NodeType) -> Type:
        """
        Получает класс ноды по типу.
        
        Args:
            node_type: Тип ноды (NodeType Enum)
        
        Returns:
            Класс ноды
        
        Raises:
            ResourceNotFoundError: Если тип не зарегистрирован
        """
        return super().get(node_type.value)
    
    def has_type(self, node_type: NodeType) -> bool:
        """
        Проверяет зарегистрирован ли тип ноды.
        
        Args:
            node_type: Тип ноды
        
        Returns:
            True если зарегистрирован
        """
        return self.has(node_type.value)


def create_default_node_registry() -> NodeRegistry:
    """
    Создаёт NodeRegistry с зарегистрированными типами нод.
    
    Вызывается при startup приложения.
    
    Returns:
        NodeRegistry со всеми типами нод
    """
    registry = NodeRegistry()
    
    registry.register(NodeType.REACT_NODE, ReactNode, {"description": "ReAct агент с LLM"})
    registry.register(NodeType.CODE, CodeNode, {"description": "Выполнение кода"})
    registry.register(NodeType.AGENT, AgentNode, {"description": "Вложенный agent"})
    registry.register(NodeType.REMOTE_AGENT, RemoteAgentNode, {"description": "Внешний A2A агент"})
    registry.register(NodeType.EXTERNAL_API, ExternalAPINode, {"description": "HTTP API вызов"})
    registry.register(NodeType.MCP, MCPNode, {"description": "MCP tool"})
    
    return registry


__all__ = ["NodeRegistry", "create_default_node_registry"]
