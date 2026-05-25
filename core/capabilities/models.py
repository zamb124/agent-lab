"""Контракты capability gateway и sandbox code runners."""

from __future__ import annotations

from typing import ClassVar, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.types import JsonObject as JsonObject
from core.types import JsonScalar as JsonScalar
from core.types import JsonValue as JsonValue

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
CodeSandboxProfile: TypeAlias = Literal["locked_down_v1"]
CodeSandboxNetworkMode: TypeAlias = Literal["capability_gateway_only"]
CodeSandboxFilesystemMode: TypeAlias = Literal["ephemeral_workspace"]


class CodeSandboxResourceLimits(BaseModel):
    """Resource limits declared for one sandbox execution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    wall_time_limit_seconds: int = Field(..., gt=0)
    cpu_time_limit_seconds: int = Field(..., gt=0)
    memory_limit_mb: int = Field(..., gt=0)
    filesystem_limit_mb: int = Field(..., ge=0)
    stdout_stderr_limit_bytes: int = Field(..., gt=0)


class CodeSandboxNetworkPolicy(BaseModel):
    """Network egress contract for sandbox code."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mode: CodeSandboxNetworkMode
    allowed_services: list[str] = Field(..., min_length=1)


class CodeSandboxFilesystemPolicy(BaseModel):
    """Filesystem contract for sandbox code."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mode: CodeSandboxFilesystemMode
    read_only_root: bool
    writable_tmp: bool


class CodeSandboxPolicy(BaseModel):
    """Single explicit sandbox contract attached to every code-runner request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    profile: CodeSandboxProfile
    limits: CodeSandboxResourceLimits
    network: CodeSandboxNetworkPolicy
    filesystem: CodeSandboxFilesystemPolicy
    allow_dynamic_code: bool
    allow_reflection: bool

    @model_validator(mode="after")
    def validate_locked_down(self) -> Self:
        if self.profile != "locked_down_v1":
            raise ValueError("sandbox.profile must be locked_down_v1")
        if self.network.mode != "capability_gateway_only":
            raise ValueError("sandbox.network.mode must be capability_gateway_only")
        if self.network.allowed_services != ["capability_gateway"]:
            raise ValueError("sandbox.network.allowed_services must be ['capability_gateway']")
        if self.filesystem.mode != "ephemeral_workspace":
            raise ValueError("sandbox.filesystem.mode must be ephemeral_workspace")
        if not self.filesystem.read_only_root:
            raise ValueError("sandbox.filesystem.read_only_root must be true")
        if not self.filesystem.writable_tmp:
            raise ValueError("sandbox.filesystem.writable_tmp must be true")
        if self.allow_dynamic_code:
            raise ValueError("sandbox.allow_dynamic_code must be false")
        if self.allow_reflection:
            raise ValueError("sandbox.allow_reflection must be false")
        return self


def locked_down_code_sandbox_policy(
    *,
    wall_time_limit_seconds: int,
    cpu_time_limit_seconds: int,
    memory_limit_mb: int,
    filesystem_limit_mb: int,
    stdout_stderr_limit_bytes: int,
) -> CodeSandboxPolicy:
    """Build the explicit locked-down policy flows sends to code runners."""
    return CodeSandboxPolicy(
        profile="locked_down_v1",
        limits=CodeSandboxResourceLimits(
            wall_time_limit_seconds=wall_time_limit_seconds,
            cpu_time_limit_seconds=cpu_time_limit_seconds,
            memory_limit_mb=memory_limit_mb,
            filesystem_limit_mb=filesystem_limit_mb,
            stdout_stderr_limit_bytes=stdout_stderr_limit_bytes,
        ),
        network=CodeSandboxNetworkPolicy(
            mode="capability_gateway_only",
            allowed_services=["capability_gateway"],
        ),
        filesystem=CodeSandboxFilesystemPolicy(
            mode="ephemeral_workspace",
            read_only_root=True,
            writable_tmp=True,
        ),
        allow_dynamic_code=False,
        allow_reflection=False,
    )


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
    channel: str = Field(..., min_length=1)
    request_id: str | None = None
    trace_id: str | None = None
    durable_execution_branch_id: str | None = Field(default=None, min_length=1)
    durable_node_schedule_sequence: int | None = Field(default=None, ge=0)
    durable_superstep_sequence: int | None = Field(default=None, ge=0)
    source_node_id: str | None = Field(default=None, min_length=1)
    source_tool_call_id: str | None = Field(default=None, min_length=1)


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
    correlation_id: str | None = Field(default=None, min_length=1)


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
    sandbox: CodeSandboxPolicy
    args: JsonObject = Field(default_factory=dict)
    state: JsonObject = Field(default_factory=dict)
    context: CapabilityExecutionContext
    capability_manifest: CapabilityManifest

    @model_validator(mode="after")
    def validate_sandbox_wall_time(self) -> Self:
        if self.sandbox.limits.wall_time_limit_seconds != self.wall_time_limit_seconds:
            raise ValueError(
                "wall_time_limit_seconds must match sandbox.limits.wall_time_limit_seconds"
            )
        return self


class CodeValidationRequest(BaseModel):
    """Запрос на compile/build валидацию пользовательского кода в language runner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: CodeExecutionKind
    language: CapabilityLanguage
    code: str = Field(..., min_length=1)
    entrypoint: str | None = Field(default=None, min_length=1)
    wall_time_limit_seconds: int = Field(..., gt=0)
    sandbox: CodeSandboxPolicy
    context: CapabilityExecutionContext
    capability_manifest: CapabilityManifest

    @model_validator(mode="after")
    def validate_sandbox_wall_time(self) -> Self:
        if self.sandbox.limits.wall_time_limit_seconds != self.wall_time_limit_seconds:
            raise ValueError(
                "wall_time_limit_seconds must match sandbox.limits.wall_time_limit_seconds"
            )
        return self


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
