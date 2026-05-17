"""
URN (Universal Resource Name) для ресурсов платформы.

Формат: urn:iman:type:id

Примеры:
- urn:iman:agent:customer_service
- urn:iman:node:summarizer
- urn:iman:tool:calculator
- urn:iman:branch:refund_processing

URN обеспечивает:
1. Явное разделение namespace (больше никаких "это tool или node?")
2. Прозрачный резолвинг ресурсов
3. Защиту от циклических зависимостей (можно отследить путь)
4. Валидацию на этапе парсинга
"""

from typing import Literal, Self, Union

from pydantic import BaseModel, Field, model_validator

# Типы ресурсов платформы
URNNamespace = Literal["iman"]
URNType = Literal["agent", "node", "tool", "branch", "variable"]


def _parse_urn_type(value: str) -> URNType:
    if value == "skill":
        return "branch"
    if value == "agent":
        return "agent"
    if value == "node":
        return "node"
    if value == "tool":
        return "tool"
    if value == "branch":
        return "branch"
    if value == "variable":
        return "variable"
    valid_types = ("agent", "node", "tool", "branch", "variable")
    raise ValueError(
        f"Неизвестный тип ресурса: '{value}'. "
        f"Допустимые значения: {', '.join(valid_types)}"
    )


class URN(BaseModel):
    """
    Базовый URN для ресурсов платформы.

    Формат: urn:namespace:type:id
    Пример: urn:iman:node:summarizer
    """

    namespace: URNNamespace = Field(default="iman", description="Namespace (всегда 'iman')")
    type: URNType = Field(..., description="Тип ресурса")
    id: str = Field(..., min_length=1, description="Идентификатор ресурса")

    @property
    def urn(self) -> str:
        """Возвращает полный URN в строковом формате"""
        return f"urn:{self.namespace}:{self.type}:{self.id}"

    @classmethod
    def parse(cls, urn_string: str) -> "URN":
        """
        Парсит строку URN в объект.

        Args:
            urn_string: Строка вида 'urn:iman:node:summarizer'

        Returns:
            URN объект

        Raises:
            ValueError: Если формат URN невалиден

        Examples:
            >>> URN.parse("urn:iman:node:summarizer")
            URN(namespace='iman', type='node', id='summarizer')
        """
        parts = urn_string.split(":")
        if len(parts) != 4:
            raise ValueError(
                f"Невалидный URN формат: '{urn_string}'. "
                f"Ожидается: 'urn:namespace:type:id'"
            )

        prefix, namespace, resource_type, resource_id = parts

        if prefix != "urn":
            raise ValueError(f"URN должен начинаться с 'urn:', получено: '{prefix}:'")

        if namespace != "iman":
            raise ValueError(f"Namespace должен быть 'iman', получено: '{namespace}'")

        parsed_type = _parse_urn_type(resource_type)

        return cls(namespace=namespace, type=parsed_type, id=resource_id)

    @classmethod
    def from_string_or_urn(cls, value: Union[str, "URN"]) -> "URN":
        """
        Конвертирует строку или URN объект в URN.

        Args:
            value: Строка URN или URN объект

        Returns:
            URN объект

        Examples:
            >>> URN.from_string_or_urn("urn:iman:node:test")
            URN(...)
            >>> URN.from_string_or_urn(URN(type="node", id="test"))
            URN(...)
        """
        if isinstance(value, URN):
            return value
        return cls.parse(value)

    def __str__(self) -> str:
        """Строковое представление - полный URN"""
        return self.urn

    def __repr__(self) -> str:
        """Представление для отладки"""
        return f"URN('{self.urn}')"

    def __eq__(self, other) -> bool:
        """Сравнение URN"""
        if isinstance(other, URN):
            return self.urn == other.urn
        if isinstance(other, str):
            return self.urn == other
        return False

    def __hash__(self) -> int:
        """Хеш для использования в dict/set"""
        return hash(self.urn)


# ============================================================================
# Специализированные URN типы
# ============================================================================


class AgentURN(URN):
    """
    URN для агентов.

    Примеры:
    - urn:iman:agent:customer_service
    - urn:iman:agent:docs_processor
    """

    type: URNType = Field(default="agent", description="Тип: agent")

    @model_validator(mode="after")
    def _validate_agent_type(self) -> Self:
        if self.type != "agent":
            raise ValueError("AgentURN.type must be 'agent'")
        return self

    @classmethod
    def create(cls, flow_id: str) -> "AgentURN":
        """
        Создаёт AgentURN из ID.

        Args:
            flow_id: ID агента

        Returns:
            AgentURN объект

        Examples:
            >>> AgentURN.create("customer_service")
            AgentURN('urn:iman:agent:customer_service')
        """
        return cls(id=flow_id)


class NodeURN(URN):
    """
    URN для нод.

    Примеры:
    - urn:iman:node:summarizer
    - urn:iman:node:validator
    """

    type: URNType = Field(default="node", description="Тип: node")

    @model_validator(mode="after")
    def _validate_node_type(self) -> Self:
        if self.type != "node":
            raise ValueError("NodeURN.type must be 'node'")
        return self

    @classmethod
    def create(cls, node_id: str) -> "NodeURN":
        """
        Создаёт NodeURN из ID.

        Args:
            node_id: ID ноды

        Returns:
            NodeURN объект

        Examples:
            >>> NodeURN.create("summarizer")
            NodeURN('urn:iman:node:summarizer')
        """
        return cls(id=node_id)


class ToolURN(URN):
    """
    URN для инструментов.

    Примеры:
    - urn:iman:tool:calculator
    - urn:iman:tool:search_web
    """

    type: URNType = Field(default="tool", description="Тип: tool")

    @model_validator(mode="after")
    def _validate_tool_type(self) -> Self:
        if self.type != "tool":
            raise ValueError("ToolURN.type must be 'tool'")
        return self

    @classmethod
    def create(cls, tool_id: str) -> "ToolURN":
        """
        Создаёт ToolURN из ID.

        Args:
            tool_id: ID инструмента

        Returns:
            ToolURN объект

        Examples:
            >>> ToolURN.create("calculator")
            ToolURN('urn:iman:tool:calculator')
        """
        return cls(id=tool_id)


class BranchURN(URN):
    """
    URN для ветки графа (branch) flow.

    Примеры:
    - urn:iman:branch:refund_processing
    - urn:iman:branch:order_tracking
    """

    type: URNType = Field(default="branch", description="Тип: branch")

    @model_validator(mode="after")
    def _validate_branch_type(self) -> Self:
        if self.type != "branch":
            raise ValueError("BranchURN.type must be 'branch'")
        return self

    @classmethod
    def create(cls, branch_id: str) -> "BranchURN":
        """
        Создаёт BranchURN из ID.

        Args:
            branch_id: ID ветки

        Returns:
            BranchURN объект

        Examples:
            >>> BranchURN.create("refund_processing")
            BranchURN('urn:iman:branch:refund_processing')
        """
        return cls(id=branch_id)


class VariableURN(URN):
    """
    URN для переменных.

    Примеры:
    - urn:iman:variable:api_key
    - urn:iman:variable:config.database.host
    """

    type: URNType = Field(default="variable", description="Тип: variable")

    @model_validator(mode="after")
    def _validate_variable_type(self) -> Self:
        if self.type != "variable":
            raise ValueError("VariableURN.type must be 'variable'")
        return self

    @classmethod
    def create(cls, variable_name: str) -> "VariableURN":
        """
        Создаёт VariableURN из имени.

        Args:
            variable_name: Имя переменной

        Returns:
            VariableURN объект

        Examples:
            >>> VariableURN.create("api_key")
            VariableURN('urn:iman:variable:api_key')
        """
        return cls(id=variable_name)


# ============================================================================
# Utility функции
# ============================================================================


def is_urn(value: str) -> bool:
    """
    Проверяет является ли строка валидным URN.

    Args:
        value: Строка для проверки

    Returns:
        True если строка - валидный URN

    Examples:
        >>> is_urn("urn:iman:node:test")
        True
        >>> is_urn("just_an_id")
        False
    """
    try:
        URN.parse(value)
        return True
    except (ValueError, Exception):
        return False


def extract_id(value: Union[str, URN]) -> str:
    """
    Извлекает ID из URN или возвращает строку как есть.

    Args:
        value: URN или строка

    Returns:
        ID ресурса

    Examples:
        >>> extract_id("urn:iman:node:summarizer")
        'summarizer'
        >>> extract_id("just_id")
        'just_id'
    """
    if isinstance(value, URN):
        return value.id

    if isinstance(value, str) and is_urn(value):
        return URN.parse(value).id

    return value


def normalize_to_urn(value: Union[str, URN], default_type: URNType) -> URN:
    """
    Нормализует значение к URN.

    Если передана строка без URN формата - добавляет тип по умолчанию.

    Args:
        value: Строка или URN
        default_type: Тип по умолчанию если value - простая строка

    Returns:
        URN объект

    Examples:
        >>> normalize_to_urn("urn:iman:node:test", "agent")
        URN('urn:iman:node:test')
        >>> normalize_to_urn("test", "node")
        URN('urn:iman:node:test')
    """
    if isinstance(value, URN):
        return value

    if is_urn(value):
        return URN.parse(value)

    # Простая строка - создаём URN с типом по умолчанию
    return URN(type=default_type, id=value)


# ============================================================================
# Export
# ============================================================================


__all__ = [
    "URN",
    "URNNamespace",
    "URNType",
    "AgentURN",
    "NodeURN",
    "ToolURN",
    "BranchURN",
    "VariableURN",
    "is_urn",
    "extract_id",
    "normalize_to_urn",
]
