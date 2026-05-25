"""Multilingual codegen tool over isolated code runners and capability-gateway."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.flows.src.services.platform_facades import get_code_runner
from apps.flows.src.tools.decorator import tool
from core.capabilities import CAPABILITY_LANGUAGES, CapabilityLanguage, JsonObject
from core.clients.llm import get_llm
from core.clients.service_client import ServiceClient
from core.company_ai import AICapability, resolve_llm_for_capability
from core.errors import CodeExecutionRuntimeError
from core.state import ExecutionState

_CAPABILITY_DOCUMENTATION_PATH = "/capability-gateway/api/v1/capabilities/documentation"
_LANGUAGES = CAPABILITY_LANGUAGES


class GeneratedCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        description="Complete source code for the requested language and requested entrypoint.",
    )


class SandboxCodegenArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(..., min_length=1, description="What the generated code must do.")
    language: CapabilityLanguage = Field(
        "python",
        description="Target runtime language.",
    )
    entrypoint: str | None = Field(
        None,
        description="Function/export name to execute. None means the first function in source.",
    )
    run_args: dict[str, Any] | None = Field(
        None,
        description="JSON object passed as args to the entrypoint(args, state) call.",
    )
    run_variables: dict[str, Any] | None = Field(
        None,
        description="JSON object merged into state.variables before execution.",
    )
    output_json_schema: str | None = Field(
        None,
        description="Optional JSON Schema text describing the expected generated-code result.",
    )
    max_iterations: int = Field(5, ge=1, le=20)
    max_doc_chars: int = Field(120_000, ge=5_000, le=500_000)
    model: str = Field(
        default="",
        description=(
            "Explicit LLM model for code generation when company llm_codegen override is not set."
        ),
    )

    @field_validator("model", mode="before")
    @classmethod
    def _model_non_empty(cls, value: Any) -> Any:
        if value is None:
            return ""
        return value

    @field_validator("run_args", "run_variables", mode="before")
    @classmethod
    def _coerce_json_object(cls, value: Any) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                raise ValueError("expected JSON object")
            return parsed
        raise ValueError(f"expected object or JSON object string, got {type(value).__name__}")


async def _language_docs(language: CapabilityLanguage, max_doc_chars: int) -> str:
    raw = await ServiceClient().get(
        "capability_gateway",
        _CAPABILITY_DOCUMENTATION_PATH,
        params={"language": language},
        timeout=30.0,
    )
    if not isinstance(raw, dict) or not isinstance(raw.get("markdown"), str):
        raise RuntimeError("capability-gateway documentation response is invalid")
    docs = str(raw["markdown"])
    if len(docs) <= max_doc_chars:
        return docs
    return docs[:max_doc_chars] + "\n\n# ... [documentation truncated by max_doc_chars]\n"


def _entrypoint_contract(language: CapabilityLanguage, entrypoint: str | None) -> str:
    if entrypoint is None:
        return "Make the first top-level function in the source the executable entrypoint with signature (args, state)"
    if language == "go":
        return f"Implement exactly: func {entrypoint}(args map[string]any, state map[string]any) (any, error)"
    if language == "csharp":
        return f"Implement exactly: async Task<object?> {entrypoint}(Dictionary<string, object?> args, Dictionary<string, object?> state)"
    if language == "python":
        return f"Implement exactly: async def {entrypoint}(args, state)"
    return f"Implement exactly: async function {entrypoint}(args, state)"


def _system_prompt(
    *,
    language: CapabilityLanguage,
    entrypoint: str | None,
    docs: str,
    output_json_schema: str | None,
) -> str:
    schema_hint = ""
    if output_json_schema and output_json_schema.strip():
        schema_hint = f"\nExpected result JSON Schema:\n{output_json_schema.strip()}\n"
    return (
        "Generate production-quality user code for Humanitec isolated code runners.\n"
        f"Target language: {language}.\n"
        f"{_entrypoint_contract(language, entrypoint)}.\n"
        "Do not import apps.* or core.*. Do not call platform internals directly.\n"
        "Use only the documented generated SDK namespaces for platform access; they are generated from the capability manifest.\n"
        "Do not use JavaScript/TypeScript export syntax; runners resolve and export the entrypoint internally.\n"
        "Return a JSON-serializable value and update state only through the provided state object.\n"
        "Reply only with structured JSON matching GeneratedCode.\n"
        f"{schema_hint}\n"
        "Capability documentation:\n"
        f"{docs}"
    )


def _execution_state_for_codegen(
    state: Any,
    run_variables: dict[str, Any] | None,
) -> ExecutionState:
    if isinstance(state, ExecutionState):
        base = state.model_copy(deep=True)
    elif isinstance(state, dict):
        base = ExecutionState.model_validate(state)
    else:
        raise ValueError("sandbox_codegen requires ExecutionState")
    if run_variables:
        base.variables = {**(base.variables or {}), **run_variables}
    return base


def _resolve_codegen_llm_kwargs(model: str) -> tuple[dict[str, Any], str]:
    resolved = resolve_llm_for_capability(
        AICapability.LLM_CODEGEN,
        include_platform_default=True,
    )
    if resolved is not None:
        return (
            {
                "provider": resolved.provider,
                "model_name": resolved.model,
                "api_key": resolved.api_key,
                "base_url": resolved.base_url,
                "folder_id": resolved.folder_id,
                "extra_request_headers": resolved.extra_request_headers,
                "extra_request_body": resolved.extra_request_body,
                "fallback_models": list(resolved.fallback_models or ()) or None,
            },
            resolved.model,
        )
    selected_model = model.strip() if model and model.strip() else ""
    if not selected_model:
        raise ValueError(
            "sandbox_codegen: platform default для capability=llm_codegen не настроен."
        )
    return {"model_name": selected_model}, selected_model


@tool(
    name="sandbox_codegen",
    description=(
        "Generate and execute code in an isolated Humanitec language runner. "
        "Supports python, javascript, typescript, go and csharp. The generated code uses capability-gateway for every platform capability."
    ),
    tags=["codegen", "sandbox", "capabilities"],
    parameters_model=SandboxCodegenArgs,
)
async def sandbox_codegen(
    task: str,
    language: CapabilityLanguage = "python",
    entrypoint: str | None = None,
    run_args: dict[str, Any] | None = None,
    run_variables: dict[str, Any] | None = None,
    output_json_schema: str | None = None,
    max_iterations: int = 5,
    max_doc_chars: int = 120_000,
    model: str = "",
    *,
    state: Any | None = None,
) -> dict[str, Any]:
    capability_language = cast(CapabilityLanguage, language)
    if capability_language not in _LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    entrypoint_name = entrypoint.strip() if isinstance(entrypoint, str) and entrypoint.strip() else None
    exec_state = _execution_state_for_codegen(state, run_variables)
    llm_kwargs, selected_model = _resolve_codegen_llm_kwargs(model)
    docs = await _language_docs(capability_language, max_doc_chars)
    llm = get_llm(state=exec_state, **llm_kwargs)
    runner = get_code_runner(language=capability_language)
    args = cast(JsonObject, dict(run_args or {}))
    trace: list[dict[str, Any]] = []
    last_code = ""
    feedback: str | None = None

    for attempt in range(1, max_iterations + 1):
        user_parts = [f"Task:\n{task}"]
        if last_code:
            user_parts.append(f"Previous code:\n```{capability_language}\n{last_code}\n```")
        if feedback:
            user_parts.append(f"Execution feedback:\n{feedback}")

        generated = await llm.chat(
            [
                {
                    "role": "system",
                    "content": _system_prompt(
                        language=capability_language,
                        entrypoint=entrypoint_name,
                        docs=docs,
                        output_json_schema=output_json_schema,
                    ),
                },
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            response_model=GeneratedCode,
            model=selected_model,
        )
        last_code = generated.code.strip()
        try:
            result = await runner.execute_tool(last_code, args, exec_state, entrypoint=entrypoint_name)
        except CodeExecutionRuntimeError as exc:
            trace.append(
                {
                    "attempt": attempt,
                    "phase": "execute",
                    "error": str(exc),
                    "payload": exc.payload,
                }
            )
            feedback = json.dumps(exc.payload, ensure_ascii=False, indent=2)
            continue
        except Exception as exc:
            trace.append(
                {
                    "attempt": attempt,
                    "phase": "execute",
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                }
            )
            feedback = f"{type(exc).__name__}: {exc}"
            continue

        trace.append({"attempt": attempt, "phase": "success"})
        return {
            "success": True,
            "language": capability_language,
            "result": result,
            "state": exec_state.model_dump(mode="json", exclude_none=False),
            "final_code": last_code,
            "attempts": attempt,
            "trace": trace,
        }

    return {
        "success": False,
        "language": capability_language,
        "result": None,
        "state": exec_state.model_dump(mode="json", exclude_none=False),
        "final_code": last_code,
        "attempts": max_iterations,
        "trace": trace,
        "error": "max_iterations_exhausted",
    }
