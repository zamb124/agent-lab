"""
URN (Universal Resource Name) для ресурсов платформы.

Формат: urn:iman:resource_type:resource_id

Примеры:
- urn:iman:flow:customer_service
- urn:iman:node:summarizer
- urn:iman:tool:calculator
- urn:iman:branch:refund_processing

URN обеспечивает:
1. Явное разделение namespace (больше никаких "это tool или node?")
2. Прозрачный резолвинг ресурсов
3. Защиту от циклических зависимостей (можно отследить путь)
4. Валидацию на этапе парсинга
"""

from __future__ import annotations

from typing import Literal, Self, override

from pydantic import BaseModel, Field, model_validator

# Типы ресурсов платформы
URNNamespace = Literal["iman"]
URNResourceType = Literal["flow", "node", "tool", "branch", "variable"]


def _parse_urn_resource_type(value: str) -> URNResourceType:
    if value == "flow":
        return "flow"
    if value == "node":
        return "node"
    if value == "tool":
        return "tool"
    if value == "branch":
        return "branch"
    if value == "variable":
        return "variable"
    valid_types = ("flow", "node", "tool", "branch", "variable")
    raise ValueError(
        f"Неизвестный тип ресурса: '{value}'. "
        + f"Допустимые значения: {', '.join(valid_types)}"
    )


class URN(BaseModel):
    """
    Базовый URN для ресурсов платформы.

    Формат: urn:namespace:resource_type:resource_id
    Пример: urn:iman:node:summarizer
    """

    namespace: URNNamespace = Field(default="iman", description="Namespace (всегда 'iman')")
    resource_type: URNResourceType = Field(..., description="Тип ресурса")
    resource_id: str = Field(..., min_length=1, description="Идентификатор ресурса")

    @property
    def urn(self) -> str:
        """Возвращает полный URN в строковом формате"""
        return f"urn:{self.namespace}:{self.resource_type}:{self.resource_id}"

    @classmethod
    def parse(cls, urn_string: str) -> "URN":
        """
        Парсит строку URN в объект.

        Аргументы:
            urn_string: Строка вида 'urn:iman:node:summarizer'

        Возвращает:
            URN объект

        Исключения:
            ValueError: Если формат URN невалиден

        Примеры:
            >>> URN.parse("urn:iman:node:summarizer")
            URN(namespace='iman', resource_type='node', resource_id='summarizer')
        """
        parts = urn_string.split(":")
        if len(parts) != 4:
            raise ValueError(
                f"Невалидный URN формат: '{urn_string}'. "
                + "Ожидается: 'urn:namespace:resource_type:resource_id'"
            )

        prefix, namespace_part, resource_type_part, resource_id = parts

        if prefix != "urn":
            raise ValueError(f"URN должен начинаться с 'urn:', получено: '{prefix}:'")

        if namespace_part != "iman":
            raise ValueError(f"Namespace должен быть 'iman', получено: '{namespace_part}'")

        namespace: URNNamespace = "iman"
        parsed_resource_type = _parse_urn_resource_type(resource_type_part)

        return cls(
            namespace=namespace,
            resource_type=parsed_resource_type,
            resource_id=resource_id,
        )

    @classmethod
    def from_string_or_urn(cls, value: str | URN) -> URN:
        """
        Конвертирует строку или URN объект в URN.

        Аргументы:
            value: Строка URN или URN объект

        Возвращает:
            URN объект

        Примеры:
            >>> URN.from_string_or_urn("urn:iman:node:test")
            URN(...)
            >>> URN.from_string_or_urn(URN(resource_type="node", resource_id="test"))
            URN(...)
        """
        if isinstance(value, URN):
            return value
        return cls.parse(value)

    @override
    def __str__(self) -> str:
        """Строковое представление - полный URN"""
        return self.urn

    @override
    def __repr__(self) -> str:
        """Представление для отладки"""
        return f"URN('{self.urn}')"

    @override
    def __hash__(self) -> int:
        """Хеш для использования в dict/set"""
        return hash(self.urn)


# ============================================================================
# Специализированные URN типы
# ============================================================================


class FlowURN(URN):
    """
    URN для flow.

    Примеры:
    - urn:iman:flow:customer_service
    - urn:iman:flow:docs_processor
    """

    resource_type: URNResourceType = Field(default="flow", description="Тип: flow")

    @model_validator(mode="after")
    def _validate_flow_resource_type(self) -> Self:
        if self.resource_type != "flow":
            raise ValueError("FlowURN.resource_type must be 'flow'")
        return self

    @classmethod
    def create(cls, flow_id: str) -> "FlowURN":
        """
        Создаёт FlowURN из flow_id.

        Аргументы:
            flow_id: ID flow

        Возвращает:
            FlowURN объект

        Примеры:
            >>> FlowURN.create("customer_service")
            FlowURN('urn:iman:flow:customer_service')
        """
        return cls(resource_id=flow_id)


class NodeURN(URN):
    """
    URN для нод.

    Примеры:
    - urn:iman:node:summarizer
    - urn:iman:node:validator
    """

    resource_type: URNResourceType = Field(default="node", description="Тип: node")

    @model_validator(mode="after")
    def _validate_node_resource_type(self) -> Self:
        if self.resource_type != "node":
            raise ValueError("NodeURN.resource_type must be 'node'")
        return self

    @classmethod
    def create(cls, node_id: str) -> "NodeURN":
        """
        Создаёт NodeURN из ID.

        Аргументы:
            node_id: ID ноды

        Возвращает:
            NodeURN объект

        Примеры:
            >>> NodeURN.create("summarizer")
            NodeURN('urn:iman:node:summarizer')
        """
        return cls(resource_id=node_id)


class ToolURN(URN):
    """
    URN для инструментов.

    Примеры:
    - urn:iman:tool:calculator
    - urn:iman:tool:search_web
    """

    resource_type: URNResourceType = Field(default="tool", description="Тип: tool")

    @model_validator(mode="after")
    def _validate_tool_resource_type(self) -> Self:
        if self.resource_type != "tool":
            raise ValueError("ToolURN.resource_type must be 'tool'")
        return self

    @classmethod
    def create(cls, tool_id: str) -> "ToolURN":
        """
        Создаёт ToolURN из ID.

        Аргументы:
            tool_id: ID инструмента

        Возвращает:
            ToolURN объект

        Примеры:
            >>> ToolURN.create("calculator")
            ToolURN('urn:iman:tool:calculator')
        """
        return cls(resource_id=tool_id)


class BranchURN(URN):
    """
    URN для ветки графа (branch) flow.

    Примеры:
    - urn:iman:branch:refund_processing
    - urn:iman:branch:order_tracking
    """

    resource_type: URNResourceType = Field(default="branch", description="Тип: branch")

    @model_validator(mode="after")
    def _validate_branch_resource_type(self) -> Self:
        if self.resource_type != "branch":
            raise ValueError("BranchURN.resource_type must be 'branch'")
        return self

    @classmethod
    def create(cls, branch_id: str) -> "BranchURN":
        """
        Создаёт BranchURN из ID.

        Аргументы:
            branch_id: ID ветки

        Возвращает:
            BranchURN объект

        Примеры:
            >>> BranchURN.create("refund_processing")
            BranchURN('urn:iman:branch:refund_processing')
        """
        return cls(resource_id=branch_id)


class VariableURN(URN):
    """
    URN для переменных.

    Примеры:
    - urn:iman:variable:api_key
    - urn:iman:variable:config.database.host
    """

    resource_type: URNResourceType = Field(default="variable", description="Тип: variable")

    @model_validator(mode="after")
    def _validate_variable_resource_type(self) -> Self:
        if self.resource_type != "variable":
            raise ValueError("VariableURN.resource_type must be 'variable'")
        return self

    @classmethod
    def create(cls, variable_name: str) -> "VariableURN":
        """
        Создаёт VariableURN из имени.

        Аргументы:
            variable_name: Имя переменной

        Возвращает:
            VariableURN объект

        Примеры:
            >>> VariableURN.create("api_key")
            VariableURN('urn:iman:variable:api_key')
        """
        return cls(resource_id=variable_name)


# ============================================================================
# Utility функции
# ============================================================================


def is_urn(value: str) -> bool:
    """
    Проверяет является ли строка валидным URN.

    Аргументы:
        value: Строка для проверки

    Возвращает:
        True если строка - валидный URN

    Примеры:
        >>> is_urn("urn:iman:node:test")
        True
        >>> is_urn("just_an_id")
        False
    """
    try:
        _ = URN.parse(value)
        return True
    except (ValueError, Exception):
        return False


def extract_resource_id(value: str | URN) -> str:
    """
    Извлекает resource_id из URN или возвращает строку как есть.

    Аргументы:
        value: URN или строка

    Возвращает:
        resource_id

    Примеры:
        >>> extract_resource_id("urn:iman:node:summarizer")
        'summarizer'
        >>> extract_resource_id("just_id")
        'just_id'
    """
    if isinstance(value, URN):
        return value.resource_id

    if is_urn(value):
        return URN.parse(value).resource_id

    return value


def normalize_to_urn(value: str | URN, default_resource_type: URNResourceType) -> URN:
    """
    Нормализует значение к URN.

    Если передана строка без URN формата - добавляет тип по умолчанию.

    Аргументы:
        value: Строка или URN
        default_resource_type: Тип по умолчанию если value - простая строка

    Возвращает:
        URN объект

    Примеры:
        >>> normalize_to_urn("urn:iman:node:test", "flow")
        URN('urn:iman:node:test')
        >>> normalize_to_urn("test", "node")
        URN('urn:iman:node:test')
    """
    if isinstance(value, URN):
        return value

    if is_urn(value):
        return URN.parse(value)

    # Простая строка - создаём URN с типом по умолчанию
    return URN(resource_type=default_resource_type, resource_id=value)


# ============================================================================
# Экспорт
# ============================================================================


__all__ = [
    "URN",
    "URNNamespace",
    "URNResourceType",
    "FlowURN",
    "NodeURN",
    "ToolURN",
    "BranchURN",
    "VariableURN",
    "is_urn",
    "extract_resource_id",
    "normalize_to_urn",
]
