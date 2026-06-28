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

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Annotated, ClassVar, Literal, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from apps.flows.src.constants.execution_limits import get_flow_execution_wall_time_cap_seconds
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue
from core.urn import extract_resource_id
from core.variables.models import VariableEntry, normalize_variables_map

from .enums import MergeMode
from .flow_speech_settings import FlowSpeechSettings
from .resource import ResourceReference
from .trigger_config import TriggerConfig

# Тип для permission: строка или список строк
Permission = str | list[str] | None


def _parse_flow_config_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}: ожидается целое число, получено bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name}: ожидается целое число, получена пустая строка")
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError(
                f"{field_name}: ожидается целое число, получено {value!r}"
            ) from exc
    raise ValueError(f"{field_name}: ожидается целое число, получено {type(value).__name__}")


class FlowType(str, Enum):
    """Тип flow"""
    LOCAL = "local"
    EXTERNAL = "external"


class ExternalAgentStatus(str, Enum):
    """Статус внешнего агента"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNHEALTHY = "unhealthy"


class FlowVariableConfig(VariableEntry):
    """
    Конфигурация переменной flow с метаданными.

    Контракт значения {value, secret} симметричен company-уровню
    (`core.variables.models.PlatformVariable`). При выполнении flow
    переменная по тому же ключу перекрывает company-переменную.
    """


def normalize_flow_variables_map(raw: Mapping[str, object]) -> dict[str, FlowVariableConfig]:
    """Нормализует scalar/wrapped JSON в dict[str, FlowVariableConfig]."""
    normalized = normalize_variables_map(raw)
    result: dict[str, FlowVariableConfig] = {}
    for key, entry in normalized.items():
        if isinstance(entry, FlowVariableConfig):
            result[key] = entry
        else:
            result[key] = FlowVariableConfig.model_validate(entry.model_dump())
    return result


def normalize_flow_variables_payload(data: object) -> object:
    """Нормализует scalar JSON variables в строгий FlowVariableConfig payload."""
    if not isinstance(data, dict):
        return data
    raw = cast(Mapping[str, object], data)
    variables = raw.get("variables")
    if not isinstance(variables, dict):
        return dict(raw)

    out = dict(raw)
    out["variables"] = normalize_flow_variables_map(cast(Mapping[str, object], variables))
    return out


EdgeConditionOperator = Literal["==", "!=", ">", "<", ">=", "<=", "in"]
EdgeCodeLanguage = Literal["python", "javascript", "typescript", "go", "csharp"]


class SimpleEdgeCondition(StrictBaseModel):
    """Типизированное условие перехода по значению из ExecutionState."""

    type: Literal["simple"] = "simple"
    variable: str = Field(..., min_length=1, description="Путь в ExecutionState")
    operator: EdgeConditionOperator = Field(..., description="Оператор сравнения")
    value: JsonValue = Field(..., description="JSON-значение для сравнения")


class CodeEdgeCondition(StrictBaseModel):
    """Типизированное условие перехода через durable code activity."""

    type: Literal["code"] = "code"
    language: EdgeCodeLanguage = Field(..., description="Язык code-condition")
    code: str = Field(..., min_length=1, description="Исходный код condition activity")
    entrypoint: str | None = Field(default=None, min_length=1, description="Entry point функции")


EdgeCondition = Annotated[SimpleEdgeCondition | CodeEdgeCondition, Field(discriminator="type")]


class Edge(StrictBaseModel):
    """
    Связь между нодами.

    condition - типизированный объект для проверки (опционально).
    Если condition не указан - безусловный переход.

    Допустимые форматы condition:
      - `{"type": "simple", "variable": str, "operator": str, "value": Any}`;
      - `{"type": "code", "language": "python|javascript|typescript|go|csharp", "code": str}`.
    """

    from_node: str = Field(..., description="ID исходной ноды")
    to_node: str | None = Field(..., description="ID целевой ноды (null = конец)")
    condition: EdgeCondition | None = Field(
        default=None,
        description="Условие перехода: simple ({type, variable, operator, value}) или code ({type, language, code}).",
    )
    contributes_to_join: bool = Field(
        default=True,
        description=(
            "При incoming_policy=all у целевой ноды: ребро участвует в AND; false = переход без ожидания остальных входов"
        ),
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)


class BranchConfig(StrictBaseModel):
    """
    Конфигурация ветки графа (варианта flow) внутри одного flow_id.

    Ветка имеет ту же структуру, что и базовый граф: entry, nodes, edges, variables.
    Для каждого поля можно указать режим применения через *_mode.
    Если branches не указаны в FlowConfig, автоматически создаётся default-ветка.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    name: str = Field(..., description="Название ветки")
    description: str = Field(default="", description="Описание ветки")
    tags: list[str] = Field(default_factory=list, description="Теги ветки")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом к ветке. Пустой список = доступ для всех",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    # Точка входа (всегда replace если указана)
    entry: str | None = Field(default=None, description="Точка входа")

    # Ноды
    nodes: dict[str, JsonObject] | None = Field(default=None, description="Ноды ветки")
    nodes_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения nodes: 'merge' или 'replace'"
    )

    # Связи между нодами
    edges: list[Edge] | None = Field(default=None, description="Связи между нодами")
    edges_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения edges: 'merge' или 'replace'"
    )

    # Переменные
    variables: dict[str, FlowVariableConfig] = Field(
        default_factory=dict, description="Переменные ветки с метаданными"
    )
    variables_mode: MergeMode = Field(
        default=MergeMode.MERGE, description="Режим применения variables: 'merge' или 'replace'"
    )

    # Ресурсы skill
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы ветки (мержатся с flow-level)",
    )
    resources_mode: MergeMode = Field(
        default=MergeMode.MERGE,
        description="Режим применения resources: 'merge' или 'replace'"
    )

    speech: FlowSpeechSettings | None = Field(
        default=None,
        description="Переопределение профиля речи для ветки (мержится поверх flow.speech)",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: object) -> object:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)


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
        "edges": [{"from_node": "main", "to_node": null}],
        "permission": ["admin", "developers"]
    }
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(json_schema_extra={"storage_prefix": "flow"})

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ - БЕЗ DEFAULTS!
    flow_id: str = Field(..., description="Уникальный идентификатор flow")
    name: str = Field(..., description="Название flow")
    type: FlowType = Field(default=FlowType.LOCAL, description="Тип flow (local/external)")

    @field_validator("flow_id", mode="before")
    @classmethod
    def validate_flow_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_resource_id(v)

    description: str = Field(default="", description="Описание flow")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: str | None) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""

    # LOCAL FLOW ПОЛЯ - обязательны для LOCAL, опциональны для EXTERNAL
    entry: str | None = Field(default=None, description="ID стартовой ноды - ОБЯЗАТЕЛЬНО для LOCAL")
    nodes: dict[str, JsonObject] | None = Field(
        default=None,
        description="Ноды графа - ОБЯЗАТЕЛЬНО для LOCAL"
    )
    edges: list[Edge] = Field(
        default_factory=list,
        description="Связи между нодами",
    )

    # EXTERNAL FLOW ПОЛЯ - обязательны для EXTERNAL, опциональны для LOCAL
    url: str | None = Field(default=None, description="Base URL внешнего flow (A2A) - ОБЯЗАТЕЛЬНО для EXTERNAL")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP-заголовки к внешнему агенту (A2A)")
    status: ExternalAgentStatus = Field(
        default=ExternalAgentStatus.INACTIVE, description="Статус внешнего flow (A2A)"
    )
    last_health_check: datetime | None = Field(
        default=None, description="Время последней проверки здоровья"
    )
    agent_card: JsonObject | None = Field(default=None, description="Кэш agent-card.json")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = доступ для всех",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("timeout", mode="before")
    @classmethod
    def validate_flow_timeout_seconds(cls, v: object) -> int | None:
        if v is None:
            return None
        iv = _parse_flow_config_int(v, "timeout")
        if iv < 1:
            raise ValueError(f"timeout: ожидается >= 1, получено {iv}")
        cap = get_flow_execution_wall_time_cap_seconds()
        if iv > cap:
            raise ValueError(f"timeout: максимум {cap}с (flow_execution_wall_time_cap_seconds), получено {iv}")
        return iv

    # Опциональные/технические поля
    version: str = Field(default="", description="Версия flow (timestamp)")
    tags: list[str] = Field(default_factory=list, description="Теги для группировки")

    variables: dict[str, FlowVariableConfig] = Field(
        default_factory=dict,
        description="Переменные flow с метаданными. @var:key резолвятся из БД",
    )

    metadata: JsonObject = Field(
        default_factory=dict,
        description=(
            "UI-метаданные flow editor (sticky_notes, layout-подсказки и пр.). "
            "Не влияет на исполнение; обновляется через PATCH /flows/{flow_id}/metadata. "
            "viewBox preference и заметки на канвасе."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: object) -> object:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)

    branches: dict[str, BranchConfig] = Field(
        default_factory=dict,
        description="Ветки flow (варианты графа). Если пусто — автоматически default-ветка",
    )
    channels: dict[str, JsonObject] = Field(
        default_factory=lambda: {"a2a": {}}, description="Каналы"
    )
    store: JsonObject = Field(default_factory=dict, description="Начальные данные")
    timeout: int | None = Field(
        default=None,
        description="Wall-clock лимит одного run flow (сек), верх снимается с flow_execution_wall_time_cap_seconds; None = default_flow_timeout_seconds",
    )
    max_retries: int = Field(default=0, description="Максимум повторов")
    source: str = Field(default="manual", description="Источник создания")
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
    hidden: bool = Field(default=False, description="Скрытый flow (не отображается в UI)")

    depends_on_flow_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Bundle-only (flow.json): flow_id агентов-зависимостей. "
            "При reload-from-bundle и company init ставятся до этого flow."
        ),
    )

    store_card_image_url: str | None = Field(
        default=None,
        description=(
            "URL обложки агента (витрина, публичные embed/лендинг). "
            "В UI задаётся загрузкой файла; при установке из bundle поле материализуется из store_card_image."
        ),
    )

    # Ресурсы flow
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы flow, доступные всем нодам"
    )

    speech: FlowSpeechSettings | None = Field(
        default=None,
        description="Профиль речи (STT/TTS/VAD) без секретов; tier ниже explicit SpeechOverride, выше company",
    )

    # Триггеры flow — точки входа (telegram, cron, webhook, email)
    triggers: dict[str, TriggerConfig] = Field(
        default_factory=dict,
        description="Триггеры flow {trigger_id: TriggerConfig}"
    )

    # Контроль доступа для UI
    public_fields: list[str] | None = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
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
