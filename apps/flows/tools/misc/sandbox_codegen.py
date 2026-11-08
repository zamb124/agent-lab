"""Мультиязычный инструмент генерации кода через capability sandbox.codegen.

LLM codegen loop и исполнение сгенерированного кода в code-runner-<lang>
выполняются в capability_gateway; тул резолвит ExecutionState-проекцию,
зовёт capability и применяет возвращённые state/platform_effects/interrupt.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.flow_ui.effects import apply_capability_platform_effects
from apps.flows.src.runners.capability_context import capability_execution_context
from apps.flows.src.runners.remote import (
    apply_runner_returned_state,
    load_sandbox_capability_manifest,
)
from apps.flows.src.runners.tool_context_view import build_tool_context_view
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.flow_interface_context import current_flow_interface
from apps.flows.src.state import ExecutionState, parse_interrupt_body_from_external_dict
from apps.flows.src.tools.decorator import tool
from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityCallRequest,
    CapabilityLanguage,
    PlatformEffectEnvelope,
)
from core.clients.capability_gateway_client import CapabilityGatewayClient
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

_LANGUAGES = CAPABILITY_LANGUAGES


class SandboxCodegenArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(..., min_length=1, description="What the generated code must do.")
    language: CapabilityLanguage = Field(
        "python",
        description="Target runtime language.",
    )
    entrypoint: str | None = Field(
        None,
        description="Function/export name to execute. None means the first function in source.",
    )
    run_args: JsonObject | None = Field(
        None,
        description="JSON object passed as args to the entrypoint(args, state) call.",
    )
    run_variables: JsonObject | None = Field(
        None,
        description="JSON object merged into state.variables before execution.",
    )
    output_json_schema: str | None = Field(
        None,
        description="Optional JSON Schema text describing the expected generated-code result.",
    )
    max_iterations: int = Field(
        5,
        ge=1,
        le=20,
        description="Max generate-execute-feedback attempts before giving up.",
    )
    max_doc_chars: int = Field(
        120_000,
        ge=5_000,
        le=500_000,
        description="Max characters of capability documentation injected into the codegen prompt.",
    )
    model: str = Field(
        default="",
        description=(
            "Explicit LLM model for code generation when company llm_codegen override is not set."
        ),
    )

    @field_validator("model", mode="before")
    @classmethod
    def _model_non_empty(cls, value: JsonValue) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("model must be a string")
        return value

    @field_validator("run_args", "run_variables", mode="before")
    @classmethod
    def _coerce_json_object(cls, value: JsonValue) -> JsonObject | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return require_json_object(value, "sandbox_codegen.json_object")
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("expected non-empty JSON object string")
            return parse_json_object(stripped, "sandbox_codegen.json_object")
        raise ValueError(f"expected object or JSON object string, got {type(value).__name__}")


def _execution_state_for_codegen(
    state: ExecutionState,
    run_variables: JsonObject | None,
) -> ExecutionState:
    base = state.model_copy(deep=True)
    if run_variables:
        base.variables = {**base.variables, **run_variables}
    return base


def _state_json(state: ExecutionState) -> JsonObject:
    return require_json_object(
        state.model_dump(mode="json", exclude_none=False),
        "sandbox_codegen.state",
    )


@tool(
    name="sandbox_codegen",
    description=(
        "Generate and execute code in an isolated Linnex language runner. "
        "Supports python, javascript, typescript, go and csharp. The generated code uses capability-gateway for every platform capability."
    ),
    tags=["misc"],
    parameters_model=SandboxCodegenArgs,
)
async def sandbox_codegen(
    task: str,
    language: CapabilityLanguage = "python",
    entrypoint: str | None = None,
    run_args: JsonObject | None = None,
    run_variables: JsonObject | None = None,
    output_json_schema: str | None = None,
    max_iterations: int = 5,
    max_doc_chars: int = 120_000,
    model: str = "",
    *,
    state: ExecutionState,
) -> JsonObject:
    capability_language = language
    if capability_language not in _LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    entrypoint_name = entrypoint.strip() if entrypoint is not None and entrypoint.strip() else None
    exec_state = _execution_state_for_codegen(state, run_variables)
    state_view = build_tool_context_view(exec_state)
    # Unrestricted token: сгенерированный код вызывает любые capabilities — как у RemoteCodeRunner.
    execution_context = capability_execution_context(state)
    wall_time = int(get_flows_settings().node_execution_wall_time_cap_seconds)
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="sandbox.codegen",
            kwargs={
                "task": task,
                "language": capability_language,
                "entrypoint": entrypoint_name,
                "run_args": run_args,
                "output_json_schema": output_json_schema,
                "max_iterations": max_iterations,
                "max_doc_chars": max_doc_chars,
                "model": model,
                "state": state_view,
                "wall_time_limit_seconds": wall_time,
            },
        ),
        timeout=float(wall_time) * (max_iterations + 1),
    )
    result = require_json_object(response.result, "sandbox_codegen.result")
    final_state = result.get("state")
    if isinstance(final_state, dict) and final_state:
        apply_runner_returned_state(exec_state, final_state)
    effects_raw = result.get("platform_effects")
    if isinstance(effects_raw, list) and effects_raw:
        envelopes = [PlatformEffectEnvelope.model_validate(item) for item in effects_raw]
        apply_capability_platform_effects(
            exec_state,
            envelopes,
            context=execution_context,
            manifest=await load_sandbox_capability_manifest(),
            interface=current_flow_interface(),
        )
    if result.get("interrupted"):
        interrupt = require_json_object(
            result.get("interrupt"), "sandbox_codegen.interrupt"
        )
        correlation_id = interrupt.get("correlation_id")
        raise FlowInterrupt(
            body=parse_interrupt_body_from_external_dict(
                require_json_object(interrupt.get("body"), "sandbox_codegen.interrupt.body")
            ),
            correlation_id=uuid.UUID(correlation_id)
            if isinstance(correlation_id, str)
            else None,
        )
    return {
        "success": True,
        "language": result.get("language", capability_language),
        "result": result.get("result"),
        "state": _state_json(exec_state),
        "final_code": result.get("final_code", ""),
        "attempts": result.get("attempts", 0),
        "trace": result.get("trace", []),
    }
