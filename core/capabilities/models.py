"""Контракты capability gateway и sandbox code runners."""

from __future__ import annotations

from typing import ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue as PydanticJsonValue

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = PydanticJsonValue
JsonObject: TypeAlias = dict[str, JsonValue]

CapabilityLanguage: TypeAlias = Literal[
    "python",
    "javascript",
    "typescript",
    "go",
    "csharp",
]
CAPABILITY_LANGUAGES: tuple[CapabilityLanguage, ...] = (
    "python",
    "javascript",
    "typescript",
    "go",
    "csharp",
)
CAPABILITY_LANGUAGE_SET: frozenset[str] = frozenset(CAPABILITY_LANGUAGES)
CapabilityExecutionMode: TypeAlias = Literal["sync", "async"]
CapabilityCallStatus: TypeAlias = Literal["ok", "interrupt"]
CodeExecutionStatus: TypeAlias = Literal["completed", "interrupted", "failed"]
CodeExecutionKind: TypeAlias = Literal["node", "tool"]


class CapabilityDefinition(BaseModel):
    """Публичное описание одной platform capability."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    execution_mode: CapabilityExecutionMode = "async"
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    languages: list[CapabilityLanguage] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sdk_namespace: str | None = Field(default=None, min_length=1)
    sdk_method: str | None = Field(default=None, min_length=1)


class CapabilityManifest(BaseModel):
    """Версионированный manifest capabilities для sandbox SDK."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    version: str = Field(..., min_length=1)
    capabilities: list[CapabilityDefinition] = Field(default_factory=list)


class CapabilitySchemaFieldDocumentation(BaseModel):
    """Описанное поле JSON Schema для capability docs/autocomplete."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    required: bool = False
    description: str = ""
    has_default: bool = False
    default_value: JsonValue = None
    enum_values: list[JsonValue] | None = None


class CapabilitySdkMethodDocumentation(BaseModel):
    """Языковой SDK method, построенный из capability manifest."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    capability_name: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    signature: str = Field(..., min_length=1)
    insert_text: str = Field(..., min_length=1)
    documentation: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    input_fields: list[CapabilitySchemaFieldDocumentation] = Field(default_factory=list)
    output_fields: list[CapabilitySchemaFieldDocumentation] = Field(default_factory=list)


class CapabilityNamespaceDocumentation(BaseModel):
    """SDK namespace для языка: files/http/tools/..."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    methods: list[str] = Field(default_factory=list)
    capability_names: list[str] = Field(default_factory=list)


class CapabilityDocumentation(BaseModel):
    """Документация capability API, построенная из manifest."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    version: str = Field(..., min_length=1)
    markdown: str = Field(..., min_length=1)
    language: CapabilityLanguage | None = None
    namespaces: list[CapabilityNamespaceDocumentation] = Field(default_factory=list)
    capabilities: list[CapabilitySdkMethodDocumentation] = Field(default_factory=list)


class CapabilityExecutionContext(BaseModel):
    """Доверенный контекст текущего вызова capability."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    execution_token: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    user_id: str | None = None
    flow_id: str = Field(..., min_length=1)
    branch_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    request_id: str | None = None
    trace_id: str | None = None


class CapabilityCallRequest(BaseModel):
    """RPC-вызов capability из language sandbox."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    context: CapabilityExecutionContext
    name: str = Field(..., min_length=1)
    args: list[JsonValue] = Field(default_factory=list)
    kwargs: JsonObject = Field(default_factory=dict)
    state: JsonObject = Field(default_factory=dict)


class CapabilityInterruptEnvelope(BaseModel):
    """Языконезависимое представление FlowInterrupt."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: str = Field(..., min_length=1)
    body: JsonObject = Field(default_factory=dict)


class CapabilityCallResponse(BaseModel):
    """Ответ capability gateway."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: CapabilityCallStatus
    result: JsonValue = None
    state: JsonObject | None = None
    interrupt: CapabilityInterruptEnvelope | None = None


class CodeExecutionRequest(BaseModel):
    """Запрос на исполнение пользовательского кода в language runner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: CodeExecutionKind
    language: CapabilityLanguage
    code: str = Field(..., min_length=1)
    entrypoint: str | None = Field(default=None, min_length=1)
    wall_time_limit_seconds: int = Field(..., gt=0)
    args: JsonObject = Field(default_factory=dict)
    state: JsonObject = Field(default_factory=dict)
    context: CapabilityExecutionContext
    capability_manifest: CapabilityManifest


class CodeValidationRequest(BaseModel):
    """Запрос на compile/build валидацию пользовательского кода в language runner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: CodeExecutionKind
    language: CapabilityLanguage
    code: str = Field(..., min_length=1)
    entrypoint: str | None = Field(default=None, min_length=1)
    wall_time_limit_seconds: int = Field(..., gt=0)
    context: CapabilityExecutionContext
    capability_manifest: CapabilityManifest


class CodeExecutionLogRecord(BaseModel):
    """Лог, собранный внутри sandbox runner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    level: Literal["debug", "info", "warning", "error"]
    message: str = Field(..., min_length=1)
    fields: JsonObject = Field(default_factory=dict)


class CodeExecutionErrorEnvelope(BaseModel):
    """Подробная ошибка исполнения sandbox-кода."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    language: CapabilityLanguage
    service: str = Field(..., min_length=1)
    stage: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    exception_type: str = Field(..., min_length=1)
    traceback: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    request_id: str | None = None
    trace_id: str | None = None


class CodeExecutionResponse(BaseModel):
    """Ответ language runner после завершения пользовательского кода."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: CodeExecutionStatus
    result: JsonValue = None
    state: JsonObject = Field(default_factory=dict)
    state_returned: bool = False
    interrupt: CapabilityInterruptEnvelope | None = None
    error: CodeExecutionErrorEnvelope | None = None
    logs: list[CodeExecutionLogRecord] = Field(default_factory=list)


class CodeValidationResponse(BaseModel):
    """Ответ language runner после compile/build валидации без выполнения кода."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    valid: bool
    error: CodeExecutionErrorEnvelope | None = None
    warnings: list[str] = Field(default_factory=list)
