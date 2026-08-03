"""Helpers for dual tool preview (model view + execution plan)."""

from __future__ import annotations

from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.provider_schema import compile_openai_strict_parameters
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

_SECRET_KEY_FRAGMENTS: tuple[str, ...] = ("secret", "token", "password", "api_key")


class ToolPreviewModelView(StrictBaseModel):
    name: str
    description: str
    parameters: JsonObject


class ToolPreviewExecutionPlan(StrictBaseModel):
    tool_id: str
    effects: list[str]
    confirmation_floor: str
    resolved_args_masked: JsonObject
    requires_approval: bool


class ToolPreviewRequest(StrictBaseModel):
    tool_id: str
    binding_overrides: JsonObject | None = None
    model_args: JsonObject | None = None


class ToolPreviewResponse(StrictBaseModel):
    model_view: ToolPreviewModelView
    execution_plan: ToolPreviewExecutionPlan


def mask_secret_like_args(args: JsonObject) -> JsonObject:
    """Redact values whose keys look like secrets (secret/token/password/api_key)."""
    masked: JsonObject = {}
    for key, value in args.items():
        key_lower = key.lower()
        if any(fragment in key_lower for fragment in _SECRET_KEY_FRAGMENTS):
            masked[key] = "***"
            continue
        if isinstance(value, dict):
            nested = require_json_object(value, f"args.{key}")
            masked[key] = mask_secret_like_args(nested)
            continue
        masked[key] = value
    return masked


def build_tool_preview(
    tool: BaseTool,
    *,
    binding_overrides: JsonObject | None,
    model_args: JsonObject | None,
) -> ToolPreviewResponse:
    resolved: dict[str, JsonValue] = {}
    if binding_overrides is not None:
        resolved.update(binding_overrides)
    if model_args is not None:
        resolved.update(model_args)
    resolved_args = require_json_object(resolved, "resolved_args")

    openai_schema = tool.to_openai_schema()
    function_raw = openai_schema.get("function")
    function_obj = require_json_object(function_raw, "openai_schema.function")
    name = function_obj.get("name")
    description = function_obj.get("description")
    if not isinstance(name, str) or not name:
        raise ValueError(f"Tool '{tool.name}' OpenAI schema missing function.name")
    if not isinstance(description, str):
        raise ValueError(f"Tool '{tool.name}' OpenAI schema missing function.description")

    parameters = compile_openai_strict_parameters(tool.parameters)
    confirmation_floor = tool.confirmation_floor
    requires_approval = confirmation_floor in {"preview", "approval"}

    return ToolPreviewResponse(
        model_view=ToolPreviewModelView(
            name=name,
            description=description,
            parameters=parameters,
        ),
        execution_plan=ToolPreviewExecutionPlan(
            tool_id=tool.name,
            effects=list(tool.effects),
            confirmation_floor=confirmation_floor,
            resolved_args_masked=mask_secret_like_args(resolved_args),
            requires_approval=requires_approval,
        ),
    )
