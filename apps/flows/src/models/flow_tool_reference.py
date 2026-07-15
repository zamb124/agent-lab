"""Строгий контракт flow, подключённого к LLM-нode как tool."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

from .enums import NodeToolCallType, NodeType
from .exception_absorb_allow import ExceptionAbsorbAllowName
from .resource import ResourceReference


def flow_tool_parameters_schema() -> JsonObject:
    """Каноническая схема аргументов flow-as-tool."""
    return {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "Запрос, передаваемый дочернему flow",
            }
        },
        "required": ["request"],
        "additionalProperties": False,
    }


class FlowToolReference(StrictBaseModel):
    """Настройка конкретного подключения внутреннего flow как LLM tool."""

    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    tool_id: str = Field(..., min_length=1)
    type: Literal[NodeType.FLOW] = NodeType.FLOW
    flow_id: str = Field(..., min_length=1)
    branch_id: str = Field(default="default", min_length=1)
    call_type: NodeToolCallType = NodeToolCallType.CALL
    name: str = ""
    description: str = ""
    parameters_schema: JsonObject = Field(default_factory=flow_tool_parameters_schema)

    input_mapping: JsonObject = Field(default_factory=dict)
    input_schema: dict[str, JsonValue] | None = None
    output_mapping: dict[str, str] | None = None
    output_schema: dict[str, JsonValue] | None = None

    tags: list[str] = Field(default_factory=list)
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    files: list[FileRef] = Field(default_factory=list)
    local_variables: dict[str, JsonValue] = Field(default_factory=dict)
    store: dict[str, JsonValue] = Field(default_factory=dict)

    incoming_policy: Literal["any", "all"] = "any"
    save_to_messages: bool = False
    message_field: str | None = None
    exception_as_response: bool = False
    exception_allow_types: list[ExceptionAbsorbAllowName] = Field(default_factory=list)
    node_timeout_seconds: int | None = Field(default=None, ge=1)
    max_visits_per_run: int | None = Field(default=None, ge=1)

    @field_validator("tool_id", "flow_id", "branch_id")
    @classmethod
    def validate_non_empty_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identifier must be a non-empty string")
        if stripped != value:
            raise ValueError("identifier must not have surrounding whitespace")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if not self.name.strip():
            self.name = self.tool_id
        schema = require_json_object(
            self.parameters_schema,
            f"flow_tool.{self.tool_id}.parameters_schema",
        )
        if schema.get("type") != "object":
            raise ValueError("flow tool parameters_schema.type must be 'object'")
        if not isinstance(schema.get("properties"), dict):
            raise ValueError("flow tool parameters_schema.properties must be an object")
        return self
