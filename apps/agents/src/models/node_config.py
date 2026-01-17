"""
Модель NodeConfig - конфигурация ноды.

Zero-Guess Architecture:
- StrictBaseModel (extra='forbid')
- NodeType Enum вместо str
- Input/Output схемы для валидации data flow
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from core.models import StrictBaseModel
from core.urn import extract_id
from .enums import NodeType
from .tool_reference import ToolReference
from .resource import ResourceReference


class ReactLoopMode(str, Enum):
    """Режим выхода из ReAct цикла"""
    
    AUTO = "auto"  # Текст без tool_calls = финальный ответ (по умолчанию)
    EXPLICIT = "explicit"  # Выход только через exit_tool


class ReactConfig(StrictBaseModel):
    """Конфигурация ReAct цикла для react_node"""
    
    loop_mode: ReactLoopMode = Field(
        default=ReactLoopMode.AUTO,
        description="Режим выхода: auto (текст = финал) или explicit (только через exit_tool)"
    )
    exit_tool: str = Field(
        default="finish",
        description="Tool который завершает цикл в режиме explicit"
    )
    max_iterations: int = Field(
        default=10,
        description="Максимум итераций перед принудительным выходом"
    )
    strict: bool = Field(
        default=True,
        description="Строгий режим: True = reminder при тексте без exit_tool, False = текст автозавершает"
    )
    reminder_message: Optional[str] = Field(
        default=None,
        description="Кастомный reminder. По умолчанию: 'Ты не вызвал tool X для завершения...'"
    )


class NodeLLMOverride(StrictBaseModel):
    """Переопределение LLM настроек для конкретной ноды."""

    model: Optional[str] = Field(default=None, description="Модель (если None - из global LLMConfig)")
    temperature: Optional[float] = Field(default=None, description="Температура генерации")
    max_tokens: Optional[int] = Field(default=None, description="Максимум токенов в ответе")
    provider: Optional[str] = Field(default=None, description="Провайдер: openai, openrouter, bothub")
    api_key: Optional[str] = Field(default=None, description="API ключ (напрямую или @var:my_key)")
    base_url: Optional[str] = Field(default=None, description="Base URL провайдера (напрямую или @var:my_url)")


class NodeConfig(StrictBaseModel):
    """
    СТРОГАЯ конфигурация ноды.
    
    Zero-Guess Architecture:
    - type: NodeType Enum (не str!)
    - description: обязательное поле
    - input_schema, output_schema для валидации data flow
    
    Поддерживаемые типы:
    - NodeType.REACT_NODE: LLM агент с ReAct циклом
    - NodeType.CODE: выполнение кода (Python, JavaScript, Go)
    - NodeType.AGENT: вложенный agent
    - NodeType.REMOTE_AGENT: внешний агент по A2A
    - NodeType.EXTERNAL_API: вызов HTTP API
    - NodeType.MCP: MCP tool
    """

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "node"}, populate_by_name=True)

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
    node_id: str = Field(..., description="Уникальный идентификатор ноды")
    type: NodeType = Field(..., description="Тип ноды - NodeType Enum")
    name: str = Field(..., description="Название ноды")
    
    @field_validator("node_id", mode="before")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_id(v)
    
    description: str = Field(default="", description="Описание ноды")
    
    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""
    
    # Data Flow контракт (опциональн, но рекомендуется)
    input_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema входных данных")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema выходных данных")
    tags: List[str] = Field(default_factory=list, description="Группы/категории")
    
    # Для react_node
    prompt: Optional[str] = Field(default=None, description="Системный промпт")
    tools: List[ToolReference] = Field(
        default_factory=list, description="Список инструментов"
    )
    llm_override: Optional[NodeLLMOverride] = Field(
        default=None, 
        description="Переопределение LLM настроек (если None - из global config)", 
        alias="llm"
    )
    react: Optional[ReactConfig] = Field(
        default=None, description="Конфигурация ReAct цикла (loop_mode, exit_tool)"
    )
    
    # Structured Output (взаимоисключающе с tools)
    structured_output: bool = Field(
        default=False,
        description="Режим structured output вместо tools (response_format json_schema)"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema для structured output (передается в response_format)"
    )
    output_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Маппинг полей JSON -> state fields. Если None - поля записываются напрямую"
    )
    
    # Для function ноды
    code: Optional[str] = Field(default=None, description="Inline Python код")
    
    # Ресурсы ноды
    resources: Dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы ноды (переопределяют agent-level)"
    )
    
    # Общее
    local_variables: Dict[str, Any] = Field(
        default_factory=dict, description="Локальные переменные"
    )
    store: Dict[str, Any] = Field(default_factory=dict, description="Начальные данные store")
    source: str = Field(default="manual", description="Источник создания")
    created_at: Optional[datetime] = Field(default=None, description="Дата создания")
    updated_at: Optional[datetime] = Field(default=None, description="Дата обновления")
    
    # Контроль доступа для UI
    public_fields: Optional[List[str]] = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )
