"""sandbox.codegen — LLM codegen loop с исполнением в code-runner-<lang>.

Весь цикл (LLM генерация → execute → feedback) исполняется в процессе
capability_gateway: billing и AI-resolver trusted, пользовательский код —
в изолированном runner по тому же CodeExecutionRequest контракту, что и flows.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability, split_provider_prefixed_model
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.billing.service import BillingService
from core.capabilities import (
    CODE_RUNNER_EXECUTE_HTTP_TIMEOUT_SLACK_SECONDS,
    CODE_SANDBOX_FILESYSTEM_LIMIT_MB,
    CODE_SANDBOX_MEMORY_LIMIT_MB,
    CODE_SANDBOX_STDOUT_STDERR_LIMIT_BYTES,
    CapabilityCallRequest,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionRequest,
    CodeExecutionResponse,
    PlatformEffectEnvelope,
    execution_token_exp,
    filter_capabilities_by_allowed,
    issue_execution_token,
    locked_down_code_sandbox_policy,
    runner_execute_endpoint,
    verify_execution_token,
)
from core.capabilities.source_sanitize import reject_forbidden_platform_imports
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.types import JsonObject, JsonValue, require_json_object


class GeneratedCode(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        description="Complete source code for the requested language and requested entrypoint.",
    )


class SandboxCodegenCapabilityArgs(BaseModel):
    """kwargs capability sandbox.codegen (state — сериализованный tool-context view)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    task: str = Field(..., min_length=1)
    language: CapabilityLanguage = "python"
    entrypoint: str | None = None
    run_args: JsonObject | None = None
    output_json_schema: str | None = None
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_doc_chars: int = Field(default=120_000, ge=5_000, le=500_000)
    model: str = ""
    state: JsonObject = Field(default_factory=dict)
    wall_time_limit_seconds: int = Field(default=120, ge=1)

    @field_validator("model", mode="before")
    @classmethod
    def _model_non_empty(cls, value: JsonValue) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("model must be a string")
        return value


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
        "Generate production-quality user code for Linnex isolated code runners.\n"
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


def _resolve_codegen_llm_selection(model: str) -> ResolvedAIModel:
    resolved = resolve_ai_model(
        AICapability.LLM_CODEGEN,
        include_platform_default=True,
    )
    if resolved is not None:
        return resolved
    selected_model = model.strip() if model and model.strip() else ""
    if not selected_model:
        raise ValueError(
            "sandbox.codegen: platform default for capability=llm_codegen is not configured."
        )
    explicit_provider, explicit_model = split_provider_prefixed_model(None, selected_model)
    resolved_model = str(explicit_model or selected_model).strip()
    if not resolved_model:
        raise ValueError("sandbox.codegen: model could not be parsed into a non-empty model")
    provider = explicit_provider or str(get_settings().llm.provider).strip()
    if not provider:
        raise ValueError("sandbox.codegen: settings.llm.provider is required for an explicit model")
    resolved = resolve_ai_model(
        AICapability.LLM_CODEGEN,
        selection=AISelection(provider=provider, model=resolved_model),
        include_platform_default=False,
    )
    if resolved is None:
        raise ValueError("sandbox.codegen: explicit provider/model could not be resolved")
    return resolved


async def invoke_sandbox_codegen(
    request: CapabilityCallRequest,
    *,
    billing_service: BillingService,
    service_client: ServiceClient,
    manifest: CapabilityManifest,
    documentation_provider: Callable[[CapabilityLanguage], Awaitable[CapabilityDocumentation]],
) -> JsonObject:
    """LLM codegen → execute в code-runner → feedback loop. Вызывается внутри active Context."""
    args = SandboxCodegenCapabilityArgs.model_validate(request.kwargs)
    entrypoint_name = (
        args.entrypoint.strip() if args.entrypoint is not None and args.entrypoint.strip() else None
    )
    claims = verify_execution_token(request.context.execution_token)
    exec_manifest = filter_capabilities_by_allowed(
        manifest,
        allowed_capabilities=claims.allowed_capabilities,
    )

    documentation = await documentation_provider(args.language)
    docs = documentation.markdown
    if len(docs) > args.max_doc_chars:
        docs = docs[: args.max_doc_chars] + "\n\n# ... [documentation truncated by max_doc_chars]\n"

    resolved_llm = _resolve_codegen_llm_selection(args.model)
    state_view: JsonObject = dict(args.state)
    variables = state_view.get("variables")
    llm = create_llm_client_from_ai_model(
        resolved_llm,
        billing_service=billing_service,
        variables=variables if isinstance(variables, dict) else None,
    )

    run_args: JsonObject = dict(args.run_args) if args.run_args is not None else {}
    trace: list[JsonObject] = []
    platform_effects: list[PlatformEffectEnvelope] = []
    last_code = ""
    feedback: str | None = None

    for attempt in range(1, args.max_iterations + 1):
        user_parts = [f"Task:\n{args.task}"]
        if last_code:
            user_parts.append(f"Previous code:\n```{args.language}\n{last_code}\n```")
        if feedback:
            user_parts.append(f"Execution feedback:\n{feedback}")

        generated = await llm.chat(
            [
                {
                    "role": "system",
                    "content": _system_prompt(
                        language=args.language,
                        entrypoint=entrypoint_name,
                        docs=docs,
                        output_json_schema=args.output_json_schema,
                    ),
                },
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            response_model=GeneratedCode,
            model=resolved_llm.model,
        )
        last_code = generated.code.strip()
        response = await _execute_in_runner(
            service_client,
            request=request,
            args=args,
            code=last_code,
            run_args=run_args,
            state_view=state_view,
            entrypoint=entrypoint_name,
            manifest=exec_manifest,
        )
        if response.status == "failed":
            trace.append(
                {
                    "attempt": attempt,
                    "phase": "execute",
                    "error": response.error.message if response.error else "execution failed",
                    "payload": (
                        require_json_object(
                            response.error.model_dump(mode="json"), "sandbox.codegen.error"
                        )
                        if response.error
                        else {}
                    ),
                }
            )
            feedback = json.dumps(
                response.error.model_dump(mode="json") if response.error else {},
                ensure_ascii=False,
                indent=2,
            )
            continue
        if response.state:
            state_view.update(response.state)
        platform_effects.extend(response.platform_effects)
        if response.status == "interrupted":
            trace.append({"attempt": attempt, "phase": "interrupted"})
            return {
                "success": False,
                "interrupted": True,
                "language": args.language,
                "interrupt": (
                    response.interrupt.model_dump(mode="json") if response.interrupt else {}
                ),
                "state": state_view,
                "platform_effects": [
                    envelope.model_dump(mode="json") for envelope in platform_effects
                ],
                "final_code": last_code,
                "attempts": attempt,
                "trace": trace,
            }
        trace.append({"attempt": attempt, "phase": "success"})
        return {
            "success": True,
            "language": args.language,
            "result": None if response.state_returned else response.result,
            "state": state_view,
            "platform_effects": [
                envelope.model_dump(mode="json") for envelope in platform_effects
            ],
            "final_code": last_code,
            "attempts": attempt,
            "trace": trace,
        }

    raise RuntimeError(
        "sandbox.codegen: max_iterations exhausted "
        + f"(attempts={args.max_iterations}, language={args.language})"
    )


async def _execute_in_runner(
    service_client: ServiceClient,
    *,
    request: CapabilityCallRequest,
    args: SandboxCodegenCapabilityArgs,
    code: str,
    run_args: JsonObject,
    state_view: JsonObject,
    entrypoint: str | None,
    manifest: CapabilityManifest,
) -> CodeExecutionResponse:
    runner_service, runner_path = runner_execute_endpoint(args.language)
    # Fresh token на каждый execute — как у RemoteCodeRunner; scope как у входящего.
    claims = verify_execution_token(request.context.execution_token)
    fresh_claims = claims.model_copy(
        update={"exp": execution_token_exp(args.wall_time_limit_seconds + 120)}
    )
    context = request.context.model_copy(
        update={"execution_token": issue_execution_token(fresh_claims)}
    )
    execution_request = CodeExecutionRequest(
        kind="tool",
        language=args.language,
        code=reject_forbidden_platform_imports(code),
        entrypoint=entrypoint,
        wall_time_limit_seconds=args.wall_time_limit_seconds,
        sandbox=locked_down_code_sandbox_policy(
            wall_time_limit_seconds=args.wall_time_limit_seconds,
            cpu_time_limit_seconds=args.wall_time_limit_seconds,
            memory_limit_mb=CODE_SANDBOX_MEMORY_LIMIT_MB,
            filesystem_limit_mb=CODE_SANDBOX_FILESYSTEM_LIMIT_MB,
            stdout_stderr_limit_bytes=CODE_SANDBOX_STDOUT_STDERR_LIMIT_BYTES,
        ),
        args=run_args,
        state=state_view,
        context=context,
        capability_manifest=manifest,
    )
    raw_response = await service_client.post(
        runner_service,
        runner_path,
        json=execution_request.model_dump(mode="json", exclude_none=True),
        timeout=float(args.wall_time_limit_seconds)
        + CODE_RUNNER_EXECUTE_HTTP_TIMEOUT_SLACK_SECONDS,
    )
    return CodeExecutionResponse.model_validate(raw_response)
