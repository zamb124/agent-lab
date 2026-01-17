"""
Модель AgentConfig - конфигурация агента.

Agent = граф:
- nodes: ноды (react_node, function, agent)
- edges: связи между нодами с условиями
- entry: точка входа

Zero-Guess Architecture:
- Использует StrictBaseModel (extra='forbid')
- Использует MergeMode Enum вместо класса
- Явные типы для всех полей
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from core.models import StrictBaseModel
from core.urn import extract_id
from .enums import MergeMode
from .resource import ResourceReference
from .trigger_config import TriggerConfig

# Тип для permission: строка или список строк
Permission = Optional[Union[str, List[str]]]


class AgentType(str, Enum):
    """Тип агента"""
    LOCAL = "local"
    EXTERNAL = "external"


class ExternalAgentStatus(str, Enum):
    """Статус внешнего агента"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNHEALTHY = "unhealthy"


class AgentVariableConfig(StrictBaseModel):
    """
    Конфигурация переменной агента с метаданными.
    
    Формат:
    {
      "value": "@var:key",
      "public": true,
      "title": "API Key",
      "description": "Ключ для доступа к API",
      "order": 1
    }
    """

    value: Any = Field(..., description="Значение переменной")
    public: bool = Field(default=False, description="Публичная переменная для agent-card")
    title: Optional[str] = Field(default=None, description="Заголовок переменной")
    description: Optional[str] = Field(default=None, description="Описание переменной")
    order: Optional[int] = Field(default=None, description="Порядок отображения")


class Edge(StrictBaseModel):
    """
    Связь между нодами.

    condition - выражение для проверки (опционально).
    Если condition не указан - безусловный переход.
    """

    from_node: str = Field(..., alias="from", description="ID исходной ноды")
    to_node: Optional[str] = Field(..., alias="to", description="ID целевой ноды (null = конец)")
    condition: Optional[str] = Field(
        default=None,
        description="Условие перехода. Примеры: 'validation.valid == true', 'stage == \"done\"'",
    )

    model_config = ConfigDict(populate_by_name=True)


class InputType(str, Enum):
    """Тип входа для теста."""
    TEXT = "text"
    FUNCTION = "function"
    NODE = "node"


class CheckType(str, Enum):
    """Тип проверки для теста."""
    STRING = "string"
    FUNCTION = "function"
    NODE = "node"


class InputConfig(StrictBaseModel):
    """
    Конфигурация входа теста.
    
    Примеры:
    - {"type": "text", "value": "Привет"}
    - {"type": "function", "value": "def generate(): return 'test'"}
    - {"type": "node", "value": "tester_node_id"}
    - {"type": "node", "node": {...}}  # inline node config как dict
    """
    type: InputType = Field(..., description="Тип входа: text, function, node")
    value: str = Field(default="", description="Текст | inline код | node_id")
    node: Optional[Dict[str, Any]] = Field(
        default=None, description="Inline нода как dict (будет преобразована в NodeConfig)"
    )
    
    @field_validator("node", mode="before")
    @classmethod
    def convert_node_to_dict(cls, v):
        """Преобразует NodeConfig в dict, если передан объект."""
        if v is None:
            return v
        # Если это уже dict, возвращаем как есть
        if isinstance(v, dict):
            return v
        # Если это NodeConfig (или любой объект с model_dump), преобразуем в dict
        if hasattr(v, "model_dump"):
            return v.model_dump()
        return v


class CheckConfig(StrictBaseModel):
    """
    Конфигурация проверки результата.
    
    Примеры:
    - {"type": "string", "value": "contains:привет"}
    - {"type": "function", "value": "def check(s,r): return 'ok' in r"}
    - {"type": "node", "value": "judge_node_id"}
    - {"type": "node", "node": {...}}  # inline node config как dict
    """
    type: CheckType = Field(..., description="Тип проверки: string, function, node")
    value: str = Field(default="", description="Checker expr | inline код | node_id")
    node: Optional[Dict[str, Any]] = Field(
        default=None, description="Inline нода-судья как dict (будет преобразована в NodeConfig)"
    )
    
    @field_validator("node", mode="before")
    @classmethod
    def convert_node_to_dict(cls, v):
        """Преобразует NodeConfig в dict, если передан объект."""
        if v is None:
            return v
        # Если это уже dict, возвращаем как есть
        if isinstance(v, dict):
            return v
        # Если это NodeConfig (или любой объект с model_dump), преобразуем в dict
        if hasattr(v, "model_dump"):
            return v.model_dump()
        return v


class TestTurn(StrictBaseModel):
    """
    Один ход теста: input + check.
    
    Примеры:
    - {"input": {"type": "text", "value": "Привет"}, "check": {"type": "string", "value": "contains:здравствуй"}}
    - {"input": {"type": "agent", "value": "tester_id"}, "check": {"type": "agent", "value": "judge_id"}}
    """
    input: InputConfig = Field(..., description="Конфигурация входа")
    check: Optional[CheckConfig] = Field(default=None, description="Конфигурация проверки (опционально)")


class TestCaseConfig(StrictBaseModel):
    """
    Унифицированный тест-кейс = список ходов (turns).
    
    Любой тест это диалог из пар [input, check]:
    - Один ход: простой тест
    - Много ходов: многошаговый диалог
    - Agent-agent: автоматический диалог с max_turns
    """
    name: str = Field(..., description="Название теста")
    description: str = Field(default="", description="Описание теста")
    skill_ids: Union[Literal["*"], List[str]] = Field(
        default="*", description="Skill IDs для теста. '*' = все"
    )
    turns: List[TestTurn] = Field(..., description="Список ходов теста")
    max_turns: int = Field(default=10, description="Макс. итераций для agent-agent")
    timeout: int = Field(default=300, description="Таймаут в секундах")


class SkillConfig(StrictBaseModel):
    """
    Конфигурация skill (навыка) агента.

    Skill имеет ту же структуру что и агент: entry, nodes, edges, variables.
    Для каждого поля можно указать режим применения через *_mode.
    Если skills не указаны в AgentConfig, автоматически создается default skill.
    """

    name: str = Field(..., description="Название skill")
    description: str = Field(default="", description="Описание skill")
    tags: List[str] = Field(default_factory=list, description="Теги skill")
    permission: List[str] = Field(
        default_factory=list,
        description="Группы с доступом к skill. Пустой список = доступ для всех",
    )
    
    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: Optional[Union[str, List[str]]]) -> List[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    # Точка входа (всегда replace если указана)
    entry: Optional[str] = Field(default=None, description="Точка входа")

    # Ноды
    nodes: Optional[Dict[str, Dict[str, Any]]] = Field(default=None, description="Ноды skill")
    nodes_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения nodes: 'merge' или 'replace'"
    )

    # Связи между нодами
    edges: Optional[List[Edge]] = Field(default=None, description="Связи между нодами")
    edges_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения edges: 'merge' или 'replace'"
    )

    # Переменные
    variables: Dict[str, Union[AgentVariableConfig, Any]] = Field(
        default_factory=dict, description="Переменные skill с метаданными"
    )
    variables_mode: MergeMode = Field(
        default=MergeMode.MERGE, description="Режим применения variables: 'merge' или 'replace'"
    )
    
    # Mock конфигурация
    mock: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Mock конфигурация для skill. Переопределяет mock агента."
    )
    
    # Ресурсы skill
    resources: Dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы skill (мержатся с agent-level)"
    )
    resources_mode: MergeMode = Field(
        default=MergeMode.MERGE,
        description="Режим применения resources: 'merge' или 'replace'"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: Any) -> Any:
        """Нормализует variables: простые значения -> AgentVariableConfig."""
        if isinstance(data, dict) and "variables" in data:
            variables = data["variables"]
            if isinstance(variables, dict):
                normalized = {}
                for key, value in variables.items():
                    if isinstance(value, dict) and "value" in value:
                        normalized[key] = value
                    else:
                        normalized[key] = {"value": value, "public": False}
                data["variables"] = normalized
        return data

    @model_validator(mode="after")
    def _convert_variables_to_objects(self) -> "SkillConfig":
        """Конвертирует variables в AgentVariableConfig объекты."""
        if isinstance(self.variables, dict):
            converted = {}
            for key, value in self.variables.items():
                if isinstance(value, AgentVariableConfig):
                    converted[key] = value
                elif isinstance(value, dict):
                    converted[key] = AgentVariableConfig(**value)
                else:
                    converted[key] = AgentVariableConfig(value=value, public=False)
            object.__setattr__(self, "variables", converted)
        return self


class AgentConfig(StrictBaseModel):
    """
    СТРОГАЯ конфигурация агента.
    
    Zero-Guess Architecture:
    - extra='forbid' - неизвестные поля = ошибка
    - НЕТ defaults для критичных полей
    - Все обязательные поля ДОЛЖНЫ быть указаны явно
    
    Структура:
    {
        "agent_id": "my_agent",
        "name": "My Agent",
        "description": "Agent description",
        "entry": "main",
        "nodes": {"main": {...}},
        "edges": [{"from": "main", "to": null}],
        "permission": ["admin", "developers"]
    }
    """

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "agent"})

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ - БЕЗ DEFAULTS!
    agent_id: str = Field(..., description="Уникальный идентификатор агента")
    name: str = Field(..., description="Название агента")
    type: AgentType = Field(default=AgentType.LOCAL, description="Тип агента (local/external)")
    
    @field_validator("agent_id", mode="before")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_id(v)
    
    description: str = Field(default="", description="Описание агента")
    
    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""
    
    # LOCAL AGENT ПОЛЯ - обязательны для LOCAL, опциональны для EXTERNAL
    entry: Optional[str] = Field(default=None, description="ID стартовой ноды - ОБЯЗАТЕЛЬНО для LOCAL")
    nodes: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Ноды графа - ОБЯЗАТЕЛЬНО для LOCAL"
    )
    edges: List[Edge] = Field(
        default_factory=list,
        description="Связи между нодами",
    )
    
    # EXTERNAL AGENT ПОЛЯ - обязательны для EXTERNAL, опциональны для LOCAL
    url: Optional[str] = Field(default=None, description="Base URL агента - ОБЯЗАТЕЛЬНО для EXTERNAL")
    auth_headers: Dict[str, str] = Field(default_factory=dict, description="Заголовки авторизации")
    status: ExternalAgentStatus = Field(
        default=ExternalAgentStatus.INACTIVE, description="Статус внешнего агента"
    )
    last_health_check: Optional[datetime] = Field(
        default=None, description="Время последней проверки здоровья"
    )
    agent_card: Optional[Dict[str, Any]] = Field(default=None, description="Кэш agent-card.json")
    permission: List[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = доступ для всех",
    )
    
    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: Optional[Union[str, List[str]]]) -> List[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v
    
    # Опциональные/технические поля
    version: str = Field(default="", description="Версия агента (timestamp)")
    tags: List[str] = Field(default_factory=list, description="Теги для группировки")

    variables: Dict[str, Union[AgentVariableConfig, Any]] = Field(
        default_factory=dict,
        description="Переменные агента с метаданными. @var:key резолвятся из БД",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: Any) -> Any:
        """Нормализует variables: простые значения -> AgentVariableConfig."""
        if isinstance(data, dict) and "variables" in data:
            variables = data["variables"]
            if isinstance(variables, dict):
                normalized = {}
                for key, value in variables.items():
                    if isinstance(value, AgentVariableConfig):
                        # Уже объект AgentVariableConfig
                        normalized[key] = value
                    elif isinstance(value, dict) and "value" in value:
                        # Уже AgentVariableConfig формат (dict)
                        normalized[key] = value
                    else:
                        # Простое значение -> AgentVariableConfig формат
                        normalized[key] = {"value": value, "public": False}
                data["variables"] = normalized
        return data

    @model_validator(mode="after")
    def _convert_variables_to_objects(self) -> "AgentConfig":
        """Конвертирует variables в AgentVariableConfig объекты."""
        if isinstance(self.variables, dict):
            converted = {}
            for key, value in self.variables.items():
                if isinstance(value, AgentVariableConfig):
                    converted[key] = value
                elif isinstance(value, dict):
                    converted[key] = AgentVariableConfig(**value)
                else:
                    converted[key] = AgentVariableConfig(value=value, public=False)
            object.__setattr__(self, "variables", converted)
        return self

    skills: Dict[str, SkillConfig] = Field(
        default_factory=dict, description="Skills агента. Если пусто - автоматически default skill"
    )
    channels: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {"a2a": {}}, description="Каналы"
    )
    store: Dict[str, Any] = Field(default_factory=dict, description="Начальные данные")
    timeout: Optional[int] = Field(default=None, description="Таймаут в секундах")
    max_retries: int = Field(default=0, description="Максимум повторов")
    source: str = Field(default="manual", description="Источник создания")
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    hidden: bool = Field(default=False, description="Скрытый агент (не отображается в UI)")
    
    # Mock конфигурация
    mock: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Mock конфигурация для агента (tools, agents, nodes, llm)"
    )
    
    # Ресурсы агента
    resources: Dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы агента, доступные всем нодам"
    )

    # Evaluation - словарь тест-кейсов {test_id: TestCaseConfig}
    evaluation: Optional[Dict[str, TestCaseConfig]] = Field(
        default=None,
        description="Тест-кейсы для оценки агента {test_id: config}"
    )
    
    # Триггеры агента - точки входа (telegram, cron, webhook, email)
    triggers: Dict[str, TriggerConfig] = Field(
        default_factory=dict,
        description="Триггеры агента {trigger_id: TriggerConfig}"
    )
    
    # Контроль доступа для UI
    public_fields: Optional[List[str]] = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )
    
    @model_validator(mode="after")
    def validate_agent_type_fields(self) -> "AgentConfig":
        """Валидация полей в зависимости от типа агента."""
        if self.type == AgentType.LOCAL:
            # LOCAL агент должен иметь entry и nodes
            if not self.entry:
                raise ValueError("LOCAL agent must have 'entry' field")
            if not self.nodes:
                raise ValueError("LOCAL agent must have 'nodes' field")
        elif self.type == AgentType.EXTERNAL:
            # EXTERNAL агент должен иметь url
            if not self.url:
                raise ValueError("EXTERNAL agent must have 'url' field")
        return self
