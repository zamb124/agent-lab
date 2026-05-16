"""
NodeRegistry - реестр типов нод.

Регистрирует и предоставляет классы нод по NodeType.
Zero-Guess: все типы нод регистрируются явно при startup.
"""

from typing import Any

from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import RUNTIME_NODE_CLASSES, BaseNode
from core.registry.base import ResourceRegistry


class NodeRegistry(ResourceRegistry[type[BaseNode]]):
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

    @staticmethod
    def _node_key(node_type: str | NodeType) -> str:
        return node_type.value if isinstance(node_type, NodeType) else node_type

    def register(
        self,
        key: str | NodeType,
        resource: type[BaseNode],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Регистрирует класс ноды.

        Args:
            node_type: Тип ноды (NodeType Enum)
            node_class: Класс ноды (наследник BaseNode)
            metadata: Дополнительные метаданные

        Raises:
            ResourceAlreadyExistsError: Если тип уже зарегистрирован
        """
        super().register(self._node_key(key), resource, metadata or {})

    def get(self, key: str | NodeType) -> type[BaseNode]:
        """
        Получает класс ноды по типу.

        Args:
            node_type: Тип ноды (NodeType Enum)

        Returns:
            Класс ноды

        Raises:
            ResourceNotFoundError: Если тип не зарегистрирован
        """
        return super().get(self._node_key(key))

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

    descriptions = {
        NodeType.LLM_NODE: "LLM агент с ReAct циклом",
        NodeType.CODE: "Выполнение кода",
        NodeType.FLOW: "Вложенный flow",
        NodeType.REMOTE_FLOW: "Внешний A2A flow",
        NodeType.EXTERNAL_API: "HTTP API вызов",
        NodeType.MCP: "MCP tool",
        NodeType.CHANNEL: "Отправка в канал (Telegram, Email, Webhook)",
        NodeType.HITL_NODE: "Оператор очереди (пауза до специалиста)",
        NodeType.RESOURCE: "Нода-ресурс на графе (pass-through)",
    }
    for node_type, node_class in RUNTIME_NODE_CLASSES.items():
        registry.register(node_type, node_class, {"description": descriptions[node_type]})

    return registry


__all__ = ["NodeRegistry", "create_default_node_registry"]
