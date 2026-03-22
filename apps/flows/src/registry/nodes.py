"""
NodeRegistry - реестр типов нод.

Регистрирует и предоставляет классы нод по NodeType.
Zero-Guess: все типы нод регистрируются явно при startup.
"""

from typing import Type, Dict

from core.registry.base import ResourceRegistry
from core.errors import ResourceNotFoundError
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import (
    LlmNode,
    CodeNode,
    FlowNode,
    RemoteFlowNode,
    ExternalAPINode,
    MCPNode,
    ChannelNode,
)


class NodeRegistry(ResourceRegistry):
    """
    Реестр классов нод по типам.
    
    При startup регистрируются все доступные типы нод:
    - NodeType.LLM_NODE → LlmNode
    - NodeType.CODE → CodeNode
    - NodeType.FLOW → FlowNode
    - и т.д.
    
    Zero-Guess: попытка получить незарегистрированный тип = ошибка.
    
    Examples:
        >>> registry = NodeRegistry()
        >>> registry.register(NodeType.LLM_NODE, LlmNode)
        >>> node_class = registry.get(NodeType.LLM_NODE)
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
    
    registry.register(NodeType.LLM_NODE, LlmNode, {"description": "LLM агент с ReAct циклом"})
    registry.register(NodeType.CODE, CodeNode, {"description": "Выполнение кода"})
    registry.register(NodeType.FLOW, FlowNode, {"description": "Вложенный flow"})
    registry.register(NodeType.REMOTE_FLOW, RemoteFlowNode, {"description": "Внешний A2A flow"})
    registry.register(NodeType.EXTERNAL_API, ExternalAPINode, {"description": "HTTP API вызов"})
    registry.register(NodeType.MCP, MCPNode, {"description": "MCP tool"})
    registry.register(NodeType.CHANNEL, ChannelNode, {"description": "Отправка в канал (Telegram, Email, Webhook)"})
    
    return registry


__all__ = ["NodeRegistry", "create_default_node_registry"]
