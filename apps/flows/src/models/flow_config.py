"""
Модель FlowConfig - конфигурация flow.

Flow = граф:
- nodes: ноды (llm_node, function, flow)
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
from typing import Any, ClassVar, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from core.models import StrictBaseModel
from core.urn import extract_id
from apps.flows.src.constants.execution_limits import get_flow_execution_wall_time_cap_seconds
from .enums import MergeMode, TestTargetType
from .resource import ResourceReference
from .trigger_config import TriggerConfig

# Тип для permission: строка или список строк
Permission = Optional[Union[str, List[str]]]


class FlowType(str, Enum):
    """Тип агента"""
    LOCAL = "local"
    EXTERNAL = "external"


class ExternalAgentStatus(str, Enum):
    """Статус внешнего агента"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNHEALTHY = "unhealthy"


class FlowVariableConfig(StrictBaseModel):
    """
    Конфигурация переменной flow с метаданными.

    Контракт значения {value, secret} симметричен company-уровню
    (`core.db.repositories.variable_repository.Variable`). При выполнении flow
    переменная по тому же ключу перекрывает company-переменную.

    Формат:
    {
      "value": "@var:key",
      "secret": false,
      "public": true,
      "title": "API Key",
      "description": "Ключ для доступа к API",
      "order": 1
    }
    """

    value: Any = Field(..., description="Значение переменной")
    secret: bool = Field(default=False, description="Скрывать значение в UI (симметрично company Variable.secret)")
    public: bool = Field(default=False, description="Публичная переменная для agent-card (A2A)")
    title: Optional[str] = Field(default=None, description="Заголовок переменной")
    description: Optional[str] = Field(default=None, description="Описание переменной")
    order: Optional[int] = Field(default=None, description="Порядок отображения")


class Edge(StrictBaseModel):
    """
    Связь между нодами.

    condition - выражение для проверки (опционально).
    Если condition не указан - безусловный переход.

    Допустимые форматы condition:
      - строка: legacy-выражение `"<variable> <op> <value>"` (например, `route == 'order'`);
      - объект `{"type": "simple", "variable": str, "operator": str, "value": Any}`;
      - объект `{"type": "python", "code": str}` — функция `def check(state) -> bool`.
    """

    from_node: str = Field(..., alias="from", description="ID исходной ноды")
    to_node: Optional[str] = Field(..., alias="to", description="ID целевой ноды (null = конец)")
    condition: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Условие перехода. Строка legacy-выражения, объект simple "
            "({type, variable, operator, value}) или python ({type, code})."
        ),
    )
    contributes_to_join: bool = Field(
        default=True,
        description=(
            "При incoming_policy=all у целевой ноды: ребро участвует в AND; false = переход без ожидания остальных входов"
        ),
    )

    model_config = ConfigDict(populate_by_name=True)


class InputType(str, Enum):
    """Тип входа для теста."""
    TEXT = "text"
    INLINE_CODE = "inline_code"
    NODE = "node"


class CheckType(str, Enum):
    """Тип проверки для теста."""
    STRING = "string"
    INLINE_CODE = "inline_code"
    NODE = "node"


class InputConfig(StrictBaseModel):
    """
    Конфигурация входа теста.
    
    Примеры:
    - {"type": "text", "value": "Привет"}
    - {"type": "inline_code", "value": "def generate(): return 'test'"}
    - {"type": "node", "value": "tester_node_id"}
    - {"type": "node", "node": {...}}  # inline node config как dict
    """
    type: InputType = Field(..., description="Тип входа: text, inline_code, node")
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
    - {"type": "inline_code", "value": "def check(s,r): return 'ok' in r"}
    - {"type": "node", "value": "judge_node_id"}
    - {"type": "node", "node": {...}}  # inline node config как dict
    """
    type: CheckType = Field(..., description="Тип проверки: string, inline_code, node")
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
    - {"input": {"type": "flow", "value": "tester_id"}, "check": {"type": "flow", "value": "judge_id"}}
    """

    __test__: ClassVar[bool] = False

    input: InputConfig = Field(..., description="Конфигурация входа")
    check: Optional[CheckConfig] = Field(default=None, description="Конфигурация проверки (опционально)")


class TestTarget(StrictBaseModel):
    """
    Цель тестирования -- что именно тестируем.
    
    Примеры:
    - {"type": "flow", "flow_id": "my_flow", "skill_id": "default"}
    - {"type": "node", "node_config": {"type": "llm_node", "prompt": "..."}}
    """

    __test__: ClassVar[bool] = False

    type: TestTargetType = Field(..., description="Тип цели: flow, node")
    
    # FLOW -- тестируем другой flow (если None, используется flow_id из контекста)
    flow_id: Optional[str] = Field(default=None, description="ID flow")
    skill_id: Optional[str] = Field(default="default", description="ID skill")
    
    # NODE -- только inline конфиг ноды
    node_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Inline конфиг ноды для тестирования"
    )


class TestCaseConfig(StrictBaseModel):
    """
    Унифицированный тест-кейс = список ходов (turns).
    
    Любой тест это диалог из пар [input, check]:
    - Один ход: простой тест
    - Много ходов: многошаговый диалог
    - Flow-flow: автоматический диалог с max_turns
    
    target определяет что тестируем:
    - None / {"type": "flow"} -- полный flow
    - {"type": "node", "node_config": {...}} -- отдельная нода
    """

    __test__: ClassVar[bool] = False

    name: str = Field(..., description="Название теста")
    description: str = Field(default="", description="Описание теста")
    
    target: Optional[TestTarget] = Field(
        default=None,
        description="Цель тестирования. None = flow из контекста"
    )
    initial_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Начальное состояние для теста (переменные, данные)"
    )
    
    skill_ids: Union[Literal["*"], List[str]] = Field(
        default="*", description="Skill IDs для теста. '*' = все"
    )
    turns: List[TestTurn] = Field(..., description="Список ходов теста")
    max_turns: int = Field(default=10, description="Макс. итераций для flow-flow")
    timeout: int = Field(default=300, description="Таймаут в секундах")


class SkillConfig(StrictBaseModel):
    """
    Конфигурация skill (навыка) агента.

    Skill имеет ту же структуру что и агент: entry, nodes, edges, variables.
    Для каждого поля можно указать режим применения через *_mode.
    Если skills не указаны в FlowConfig, автоматически создаётся default skill.
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
    variables: Dict[str, Union[FlowVariableConfig, Any]] = Field(
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
        description="Ресурсы skill (мержатся с flow-level)"
    )
    resources_mode: MergeMode = Field(
        default=MergeMode.MERGE,
        description="Режим применения resources: 'merge' или 'replace'"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: Any) -> Any:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
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
        """Конвертирует variables в FlowVariableConfig объекты."""
        if isinstance(self.variables, dict):
            converted = {}
            for key, value in self.variables.items():
                if isinstance(value, FlowVariableConfig):
                    converted[key] = value
                elif isinstance(value, dict):
                    converted[key] = FlowVariableConfig(**value)
                else:
                    converted[key] = FlowVariableConfig(value=value, public=False)
            object.__setattr__(self, "variables", converted)
        return self


class FlowConfig(StrictBaseModel):
    """
    СТРОГАЯ конфигурация агента.
    
    Zero-Guess Architecture:
    - extra='forbid' - неизвестные поля = ошибка
    - НЕТ defaults для критичных полей
    - Все обязательные поля ДОЛЖНЫ быть указаны явно
    
    Структура:
    {
        "flow_id": "my_flow",
        "name": "My Agent",
        "description": "Agent description",
        "entry": "main",
        "nodes": {"main": {...}},
        "edges": [{"from": "main", "to": null}],
        "permission": ["admin", "developers"]
    }
    """

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "flow"})

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ - БЕЗ DEFAULTS!
    flow_id: str = Field(..., description="Уникальный идентификатор flow")
    name: str = Field(..., description="Название flow")
    type: FlowType = Field(default=FlowType.LOCAL, description="Тип flow (local/external)")
    
    @field_validator("flow_id", mode="before")
    @classmethod
    def validate_flow_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_id(v)
    
    description: str = Field(default="", description="Описание flow")
    
    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""
    
    # LOCAL FLOW ПОЛЯ - обязательны для LOCAL, опциональны для EXTERNAL
    entry: Optional[str] = Field(default=None, description="ID стартовой ноды - ОБЯЗАТЕЛЬНО для LOCAL")
    nodes: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Ноды графа - ОБЯЗАТЕЛЬНО для LOCAL"
    )
    edges: List[Edge] = Field(
        default_factory=list,
        description="Связи между нодами",
    )
    
    # EXTERNAL FLOW ПОЛЯ - обязательны для EXTERNAL, опциональны для LOCAL
    url: Optional[str] = Field(default=None, description="Base URL внешнего flow (A2A) - ОБЯЗАТЕЛЬНО для EXTERNAL")
    auth_headers: Dict[str, str] = Field(default_factory=dict, description="Заголовки авторизации")
    status: ExternalAgentStatus = Field(
        default=ExternalAgentStatus.INACTIVE, description="Статус внешнего flow (A2A)"
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

    @field_validator("timeout", mode="before")
    @classmethod
    def validate_flow_timeout_seconds(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        iv = int(v)
        if iv < 1:
            raise ValueError(f"timeout: ожидается >= 1, получено {iv}")
        cap = get_flow_execution_wall_time_cap_seconds()
        if iv > cap:
            raise ValueError(f"timeout: максимум {cap}с (flow_execution_wall_time_cap_seconds), получено {iv}")
        return iv
    
    # Опциональные/технические поля
    version: str = Field(default="", description="Версия flow (timestamp)")
    tags: List[str] = Field(default_factory=list, description="Теги для группировки")

    variables: Dict[str, Union[FlowVariableConfig, Any]] = Field(
        default_factory=dict,
        description="Переменные flow с метаданными. @var:key резолвятся из БД",
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "UI-метаданные flow editor (sticky_notes, layout-подсказки и пр.). "
            "Не влияет на исполнение; обновляется через PATCH /flows/{flow_id}/metadata."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: Any) -> Any:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        if isinstance(data, dict) and "variables" in data:
            variables = data["variables"]
            if isinstance(variables, dict):
                normalized = {}
                for key, value in variables.items():
                    if isinstance(value, FlowVariableConfig):
                        # Уже объект FlowVariableConfig
                        normalized[key] = value
                    elif isinstance(value, dict) and "value" in value:
                        # Уже FlowVariableConfig формат (dict)
                        normalized[key] = value
                    else:
                        # Простое значение -> FlowVariableConfig формат
                        normalized[key] = {"value": value, "public": False}
                data["variables"] = normalized
        return data

    @model_validator(mode="after")
    def _convert_variables_to_objects(self) -> "FlowConfig":
        """Конвертирует variables в FlowVariableConfig объекты."""
        if isinstance(self.variables, dict):
            converted = {}
            for key, value in self.variables.items():
                if isinstance(value, FlowVariableConfig):
                    converted[key] = value
                elif isinstance(value, dict):
                    converted[key] = FlowVariableConfig(**value)
                else:
                    converted[key] = FlowVariableConfig(value=value, public=False)
            object.__setattr__(self, "variables", converted)
        return self

    skills: Dict[str, SkillConfig] = Field(
        default_factory=dict, description="Skills flow. Если пусто - автоматически default skill"
    )
    channels: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {"a2a": {}}, description="Каналы"
    )
    store: Dict[str, Any] = Field(default_factory=dict, description="Начальные данные")
    timeout: Optional[int] = Field(
        default=None,
        description="Wall-clock лимит одного run flow (сек), верх снимается с flow_execution_wall_time_cap_seconds; None = default_flow_timeout_seconds",
    )
    max_retries: int = Field(default=0, description="Максимум повторов")
    source: str = Field(default="manual", description="Источник создания")
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    hidden: bool = Field(default=False, description="Скрытый flow (не отображается в UI)")
    
    # Mock конфигурация
    mock: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Mock конфигурация (tools, flows, nodes, llm)"
    )
    
    # Ресурсы flow
    resources: Dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы flow, доступные всем нодам"
    )

    # Evaluation - словарь тест-кейсов {test_id: TestCaseConfig}
    evaluation: Optional[Dict[str, TestCaseConfig]] = Field(
        default=None,
        description="Тест-кейсы для оценки flow {test_id: config}"
    )
    
    # Триггеры flow — точки входа (telegram, cron, webhook, email)
    triggers: Dict[str, TriggerConfig] = Field(
        default_factory=dict,
        description="Триггеры flow {trigger_id: TriggerConfig}"
    )
    
    # Контроль доступа для UI
    public_fields: Optional[List[str]] = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )

    # Метаданные UI flow: sticky_notes на канвасе, дополнительные UX-данные.
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="UI-метаданные flow (sticky_notes, viewBox preference, заметки)"
    )
    
    @model_validator(mode="after")
    def validate_flow_type_fields(self) -> "FlowConfig":
        """Валидация полей в зависимости от типа flow."""
        if self.type == FlowType.LOCAL:
            if not self.entry:
                raise ValueError("LOCAL flow must have 'entry' field")
            if not self.nodes:
                raise ValueError("LOCAL flow must have 'nodes' field")
        elif self.type == FlowType.EXTERNAL:
            if not self.url:
                raise ValueError("EXTERNAL flow must have 'url' field")
        return self
