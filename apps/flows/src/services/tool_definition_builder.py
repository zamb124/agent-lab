"""Build ToolDefinition from a process BaseTool instance."""

from __future__ import annotations

from apps.flows.src.models.tool_contracts import (
    ConfirmationFloor,
    ToolArgumentSource,
    ToolDefinition,
    ToolEffect,
    ToolIdempotency,
)
from apps.flows.src.tools.base import BaseTool, sanitize_tool_name
from core.types import JsonObject, require_json_object

BUILTIN_TOOL_DEFINITION_VERSION = 1
BUILTIN_TOOL_DEFINITION_SEMVER = "1.0.0"

_EMPTY_OBJECT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_EFFECTS: tuple[ToolEffect, ...] = (
    "read",
    "create",
    "update",
    "delete",
    "external_send",
    "financial",
    "admin",
    "code_execute",
)
_CONFIRMATION_FLOORS: tuple[ConfirmationFloor, ...] = ("none", "preview", "approval")
_IDEMPOTENCY: tuple[ToolIdempotency, ...] = ("none", "supported", "required")
_ARGUMENT_SOURCES: tuple[ToolArgumentSource, ...] = ("model", "binding", "runtime", "secret_ref")


def _tool_effect(value: str, detail: str) -> ToolEffect:
    for option in _EFFECTS:
        if option == value:
            return option
    raise ValueError(detail)


def _confirmation_floor(value: str, detail: str) -> ConfirmationFloor:
    for option in _CONFIRMATION_FLOORS:
        if option == value:
            return option
    raise ValueError(detail)


def _idempotency(value: str, detail: str) -> ToolIdempotency:
    for option in _IDEMPOTENCY:
        if option == value:
            return option
    raise ValueError(detail)


def _argument_source(value: str, detail: str) -> ToolArgumentSource:
    for option in _ARGUMENT_SOURCES:
        if option == value:
            return option
    raise ValueError(detail)


def build_tool_definition_from_base_tool(tool: BaseTool) -> ToolDefinition:
    """Map BaseTool metadata into an immutable ToolDefinition contract."""
    tool_name = tool.name.strip()
    if not tool_name:
        raise ValueError("BaseTool.name is required")
    description = tool.description.strip()
    if not description:
        raise ValueError(f"BaseTool '{tool_name}' description is required")

    input_schema = require_json_object(tool.parameters, f"tool.{tool_name}.parameters")
    if input_schema.get("type") != "object":
        raise ValueError(
            f"BaseTool '{tool_name}' parameters root type must be object, "
            + f"got {input_schema.get('type')!r}"
        )

    if tool.output_schema is None:
        canonical_output: JsonObject = dict(_EMPTY_OBJECT_SCHEMA)
    else:
        canonical_output = require_json_object(
            tool.output_schema,
            f"tool.{tool_name}.output_schema",
        )
        if canonical_output.get("type") != "object":
            raise ValueError(
                f"BaseTool '{tool_name}' output_schema root type must be object, "
                + f"got {canonical_output.get('type')!r}"
            )

    effects: list[ToolEffect] = [
        _tool_effect(effect, f"BaseTool '{tool_name}' has unknown effect: {effect!r}")
        for effect in tool.effects
    ]
    confirmation_floor = _confirmation_floor(
        tool.confirmation_floor,
        f"BaseTool '{tool_name}' has unknown confirmation_floor: {tool.confirmation_floor!r}",
    )
    idempotency = _idempotency(
        tool.idempotency,
        f"BaseTool '{tool_name}' has unknown idempotency: {tool.idempotency!r}",
    )
    argument_sources: dict[str, ToolArgumentSource] = {
        arg_name: _argument_source(
            source,
            f"BaseTool '{tool_name}' argument {arg_name!r} has unknown source: {source!r}",
        )
        for arg_name, source in tool.argument_sources.items()
    }

    provenance: JsonObject = {
        "owner": "platform",
        "trust": "platform",
        "semver": BUILTIN_TOOL_DEFINITION_SEMVER,
    }

    return ToolDefinition(
        definition_id=tool_name,
        version=BUILTIN_TOOL_DEFINITION_VERSION,
        machine_name=sanitize_tool_name(tool_name),
        title=tool_name,
        description=description,
        canonical_input_schema=input_schema,
        canonical_output_schema=canonical_output,
        argument_sources=argument_sources,
        effects=effects,
        required_scopes=[],
        confirmation_floor=confirmation_floor,
        idempotency=idempotency,
        executor_kind="trusted_builtin",
        limits=None,
        provenance=provenance,
    )
