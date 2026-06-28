"""
Канонический payload и модели переменных платформы.

Один доменный контракт переменной для всех слоёв:
- ``VariableEntry`` / ``VariableMap`` — рантайм-payload (flow, branch, WorkItem snapshot).
- ``PlatformVariable`` — хранимая версионируемая переменная компании (secrets-сервис):
  static / expression значение + scoped overrides + признак секрета и доступа.
- ``ResolutionContext`` — контекст запуска (executor), по которому движок выбирает scope.

Единственное отличие секретной переменной — её значение шифруется в хранилище и
расшифровывается лениво (на старте flow или по явному запросу с проверкой доступа).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import cast

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonValue, require_json_object, require_json_value


class VariableEntry(StrictBaseModel):
    value: JsonValue = Field(..., description="Значение переменной")
    secret: bool = Field(default=False, description="Скрывать значение в UI")
    public: bool = Field(default=False, description="Публичная переменная для agent-card (A2A)")
    title: str | None = Field(default=None, description="Заголовок переменной")
    description: str | None = Field(default=None, description="Описание переменной")
    order: int | None = Field(default=None, description="Порядок отображения")


VariableMap = dict[str, VariableEntry]


class VariableValueKind(str, Enum):
    """Тип значения переменной."""

    STATIC = "static"
    EXPRESSION = "expression"


class ScopeField(str, Enum):
    """Поле контекста запуска, по которому матчится scope override."""

    COMPANY_ID = "company_id"
    USER_ID = "user_id"
    NAMESPACE = "namespace"
    CHANNEL = "channel"
    VAR = "var"


class ScopeOp(str, Enum):
    """Оператор сравнения условия scope override."""

    EQ = "eq"
    IN = "in"
    EXISTS = "exists"


class ScopeCondition(StrictBaseModel):
    """Условие применения scope override.

    ``field=var`` сравнивает значение другой переменной (``ref_key``) — это создаёт
    зависимость между переменными, учитываемую движком при топосорте.
    """

    field: ScopeField
    op: ScopeOp = ScopeOp.EQ
    ref_key: str | None = Field(
        default=None,
        description="Ключ другой переменной для field=var",
    )
    value: JsonValue = Field(
        default=None,
        description="Сравниваемое значение (скаляр для eq/exists, список для in)",
    )


class VariableValueSpec(StrictBaseModel):
    """Базовое значение переменной: статическое или выражение со ссылками."""

    value_kind: VariableValueKind = VariableValueKind.STATIC
    value: JsonValue = Field(
        default=None,
        description="Статическое значение (для value_kind=static); может содержать @var:/@ctx: токены",
    )
    expression: str | None = Field(
        default=None,
        description="Шаблон-выражение со ссылками @var:/@ctx: (для value_kind=expression)",
    )


class VariableScopeOverride(VariableValueSpec):
    """Перекрытие значения переменной при выполнении условий контекста."""

    match: list[ScopeCondition] = Field(default_factory=list)
    priority: int = Field(
        default=0,
        description="Чем выше — тем раньше проверяется; первый полностью совпавший побеждает",
    )


class VariableValuePayload(StrictBaseModel):
    """Полное значение переменной: база + упорядоченные scoped overrides.

    Для секретной переменной этот payload целиком шифруется в хранилище.
    """

    base: VariableValueSpec = Field(default_factory=VariableValueSpec)
    scopes: list[VariableScopeOverride] = Field(default_factory=list)


class PlatformVariable(StrictBaseModel):
    """Каноническая версионируемая переменная компании (источник истины — secrets-сервис)."""

    variable_key: str
    company_id: str
    version: int = Field(default=1, ge=1)
    payload: VariableValuePayload = Field(default_factory=VariableValuePayload)
    secret: bool = Field(default=False, description="Значение шифруется в хранилище и маскируется")
    shared_for_execution: bool = Field(
        default=False,
        description="Секрет может использоваться при запуске flow любым исполнителем компании",
    )
    public: bool = Field(default=False, description="Публичная переменная для agent-card (A2A)")
    created_by: str | None = Field(default=None, description="user_id владельца переменной")
    title: str | None = None
    description: str = ""
    order: int | None = None
    groups: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResolutionContext(StrictBaseModel):
    """Контекст исполнителя, по которому движок выбирает scope и резолвит @ctx:."""

    company_id: str
    user_id: str | None = None
    namespace: str | None = None
    channel: str | None = None

    def field_value(self, field: ScopeField) -> JsonValue:
        match field:
            case ScopeField.COMPANY_ID:
                return self.company_id
            case ScopeField.USER_ID:
                return self.user_id
            case ScopeField.NAMESPACE:
                return self.namespace
            case ScopeField.CHANNEL:
                return self.channel
            case ScopeField.VAR:
                raise ValueError("ScopeField.VAR резолвится через значение другой переменной, не из контекста")


class ResolvedVariable(StrictBaseModel):
    """Переменная для движка резолвинга: payload с расшифрованным значением, если доступ разрешён."""

    variable_key: str
    version: int
    secret: bool
    shared_for_execution: bool
    public: bool
    resolvable: bool = Field(
        default=True,
        description="False для секрета без доступа у текущего исполнителя — значение не отдаётся",
    )
    payload: VariableValuePayload | None = Field(
        default=None,
        description="None, если resolvable=False (значение не раскрывается)",
    )


def normalize_variables_map(raw: Mapping[str, object]) -> VariableMap:
    """Нормализует scalar/wrapped JSON в строгий VariableMap."""
    result: VariableMap = {}
    for key, entry_raw in raw.items():
        if isinstance(entry_raw, VariableEntry):
            result[key] = entry_raw
            continue
        if isinstance(entry_raw, Mapping):
            entry_mapping = cast(Mapping[str, object], entry_raw)
            if "value" in entry_mapping:
                result[key] = VariableEntry.model_validate(dict(entry_mapping))
            else:
                entry_object = require_json_object(entry_mapping, f"variables.{key}")
                result[key] = VariableEntry(
                    value=require_json_value(entry_object, f"variables.{key}"),
                    public=False,
                )
            continue
        result[key] = VariableEntry(
            value=require_json_value(entry_raw, f"variables.{key}"),
            public=False,
        )
    return result


def variable_map_to_prompt_values(variables: VariableMap) -> dict[str, JsonValue]:
    """Plain map для prompt-editor: unwrap VariableEntry.value."""
    prompt_values: dict[str, JsonValue] = {}
    for key, entry in variables.items():
        prompt_values[key] = entry.value
    return prompt_values
