"""HTTP/WS контракты code editor: один payload на REST и command-router."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.flows.src.runtime.state_diff import DiffItem as StateDiffItem
from core.docs.models import CodeTemplate
from core.types import JsonObject, JsonValue


class CodeDocumentationPayload(BaseModel):
    language: str = "python"
    perspective: str = "editor"
    include_runtime_namespace_extras: bool = False


class CodeDocumentationResponse(BaseModel):
    markdown: str
    language: str


class CodeTemplatesPayload(BaseModel):
    language: str = "python"
    category: str | None = None
    node_type: str | None = None
    tags: str | None = None


class TemplatesResponse(BaseModel):
    templates: list[CodeTemplate]


class CodeEditorStatePayload(BaseModel):
    flow_id: str = Field(min_length=1)
    branch_id: str = "default"


class CodeSourcePayload(BaseModel):
    function_path: str = Field(min_length=1)


class SourceResponse(BaseModel):
    path: str
    source: str | None
    error: str | None = None


class FlowFunctionInfo(BaseModel):
    name: str
    path: str
    doc: str | None = None


class CodeFlowFunctionsPayload(BaseModel):
    flow_id: str = Field(min_length=1)


class FlowFunctionsResponse(BaseModel):
    flow_id: str
    functions: list[FlowFunctionInfo]


class CodeToolSourcePayload(BaseModel):
    tool_path: str = Field(min_length=1)


class ValidateRequest(BaseModel):
    code: str
    node_type: str | None = "code"
    kind: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class ValidateResponse(BaseModel):
    valid: bool
    error: str | None = None
    warnings: list[str] = []
    stage: str | None = None
    service: str | None = None
    exception_type: str | None = None


class ParseSignatureRequest(BaseModel):
    code: str
    func_name: str | None = None


class ParameterInfo(BaseModel):
    type: str
    description: str = ""
    default: JsonValue = None
    required: bool = True


class ParseSignatureResponse(BaseModel):
    success: bool
    func_name: str | None = None
    parameters: dict[str, ParameterInfo] = {}
    parameters_schema: JsonObject | None = None
    error: str | None = None


class ExecuteRequest(BaseModel):
    node_type: str = "code"
    node_config: JsonObject = Field(default_factory=dict)
    code: str | None = None
    state: JsonObject
    args: JsonObject = Field(default_factory=dict)
    entrypoint: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class ExecuteResponse(BaseModel):
    success: bool
    input_state: JsonObject | None = None
    output_state: JsonObject | None = None
    diff: list[StateDiffItem] = []
    error: str | None = None
    error_payload: JsonObject | None = None
    duration_ms: int = 0
