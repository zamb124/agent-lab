"""Canonical tool contract models (definition, binding, revision, grant, result)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

ToolArgumentSource = Literal["model", "binding", "runtime", "secret_ref"]
ToolEffect = Literal[
    "read",
    "create",
    "update",
    "delete",
    "external_send",
    "financial",
    "admin",
    "code_execute",
]
ToolIdempotency = Literal["none", "supported", "required"]
ConfirmationFloor = Literal["none", "preview", "approval"]
ToolExecutorKind = Literal["trusted_builtin", "sandbox_code", "mcp", "flow"]


class ToolDefinition(StrictBaseModel):
    """Immutable versioned platform capability contract."""

    definition_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    machine_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    canonical_input_schema: JsonObject
    canonical_output_schema: JsonObject
    argument_sources: dict[str, ToolArgumentSource] = Field(default_factory=dict)
    effects: list[ToolEffect] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    confirmation_floor: ConfirmationFloor = "none"
    idempotency: ToolIdempotency = "none"
    executor_kind: ToolExecutorKind
    limits: JsonObject | None = None
    provenance: JsonObject | None = None


class ToolBinding(StrictBaseModel):
    """Flow/node scoped editable projection over a pinned ToolDefinition."""

    binding_id: str = Field(..., min_length=1)
    definition_id: str = Field(..., min_length=1)
    definition_version: int = Field(..., ge=1)
    flow_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    llm_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""
    parameter_bindings: JsonObject = Field(default_factory=dict)
    model_schema_projection: JsonObject = Field(default_factory=dict)
    result_projection: list[str] = Field(default_factory=list)
    confirmation_override: ConfirmationFloor | None = None
    budgets: JsonObject | None = None
    enabled: bool = True


class ToolRevision(StrictBaseModel):
    """Immutable executor artifact revision (user code, MCP pin, flow pin)."""

    revision_id: str = Field(..., min_length=1)
    definition_id: str = Field(..., min_length=1)
    definition_version: int = Field(..., ge=1)
    executor_kind: ToolExecutorKind
    source_hash: str = Field(..., min_length=1)
    metadata: JsonObject = Field(default_factory=dict)


class ToolGrantClaims(StrictBaseModel):
    """Short-lived server-issued grant claims for a single tool invocation."""

    iss: str = Field(..., min_length=1)
    aud: str = Field(..., min_length=1)
    jti: str = Field(..., min_length=1)
    iat: int = Field(..., ge=0)
    nbf: int = Field(..., ge=0)
    exp: int = Field(..., gt=0)
    actor_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    flow_id: str = Field(..., min_length=1)
    branch_id: str = Field(..., min_length=1)
    source_node_id: str = Field(..., min_length=1)
    tool_call_id: str = Field(..., min_length=1)
    definition_id: str = Field(..., min_length=1)
    definition_version: int = Field(..., ge=1)
    binding_id: str | None = None
    allowed_capabilities: list[JsonObject] = Field(default_factory=list)
    max_calls: int = Field(default=1, ge=1)
    max_cost: float | None = Field(default=None, ge=0)
    deadline_unix: int | None = Field(default=None, ge=0)
    approval_id: str | None = None
    approved_argument_hash: str | None = None


class ToolErrorBody(StrictBaseModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    retryable: bool
    field: str | None = None


class ToolResultEnvelope(StrictBaseModel):
    ok: bool
    data: JsonValue | None = None
    error: ToolErrorBody | None = None

    @model_validator(mode="after")
    def _validate_ok_error_shape(self) -> ToolResultEnvelope:
        if self.ok:
            if self.error is not None:
                raise ValueError("ok=true must not include error")
            return self
        if self.error is None:
            raise ValueError("ok=false requires error")
        return self
