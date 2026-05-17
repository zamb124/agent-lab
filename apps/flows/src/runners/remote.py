"""Remote code runner client для isolated code-runner сервисов."""

from __future__ import annotations

from typing import cast, override

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.runners.base import BaseCodeRunner
from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionKind,
    CodeExecutionRequest,
    CodeExecutionResponse,
    JsonObject,
    JsonValue,
    execution_token_exp,
    issue_execution_token,
)
from core.capabilities.source_sanitize import strip_forbidden_platform_import_lines
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.errors import CodeExecutionRuntimeError
from core.logging import get_log_context, get_logger
from core.state import ExecutionState, parse_interrupt_body_from_external_dict
from core.state.mutation_policy import (
    assert_frozen_fields_unchanged,
    snapshot_frozen_fields,
)
from core.tracing.operation_span import traced_operation

CAPABILITY_MANIFEST_PATH = "/capability-gateway/api/v1/capabilities/manifest"

RUNNER_EXECUTE_PATHS: dict[str, tuple[str, str]] = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/execute"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/execute"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/execute"),
}

logger = get_logger(__name__)


class RemoteCodeRunner(BaseCodeRunner):
    """BaseCodeRunner adapter over isolated code-runner HTTP services."""

    language: str = "remote"

    def __init__(self, language: str):
        if language not in RUNNER_EXECUTE_PATHS:
            raise ValueError(f"Unsupported code runner language: {language}")
        self._language: CapabilityLanguage = cast(CapabilityLanguage, language)
        self._client: ServiceClient = ServiceClient()

    @override
    async def execute(
        self,
        code: str,
        state: ExecutionState,
        func_name: str | None = None,
    ) -> JsonValue:
        response = await self._execute_remote(
            code=code,
            state=state,
            args={},
            entrypoint=func_name,
            kind="node",
        )
        if response.state_returned:
            return None
        return response.result

    @override
    async def execute_tool(
        self,
        code: str,
        args: JsonObject,
        state: ExecutionState | None = None,
        entrypoint: str | None = None,
    ) -> JsonValue:
        if state is None:
            raise ValueError("Remote code execution requires ExecutionState")
        response = await self._execute_remote(
            code=code,
            state=state,
            args=args,
            entrypoint=entrypoint,
            kind="tool",
        )
        if response.state_returned:
            return None
        return response.result

    @override
    def validate(self, code: str) -> tuple[bool, str | None]:
        if not code.strip():
            return (False, "Код пустой")
        return (True, None)

    async def _execute_remote(
        self,
        *,
        code: str,
        state: ExecutionState,
        args: JsonObject,
        entrypoint: str | None,
        kind: CodeExecutionKind,
    ) -> CodeExecutionResponse:
        runner_service, runner_path = self._runner_endpoint()
        manifest = await self._load_manifest()
        context = self._execution_context(state)
        request = CodeExecutionRequest(
            kind=kind,
            language=self._language,
            code=strip_forbidden_platform_import_lines(code),
            entrypoint=entrypoint,
            wall_time_limit_seconds=get_flows_settings().node_execution_wall_time_cap_seconds,
            args=args,
            state=cast(JsonObject, state.model_dump(mode="json", exclude_none=False)),
            context=context,
            capability_manifest=manifest,
        )
        frozen_snapshot = snapshot_frozen_fields(state)
        async with traced_operation(
            "flows.code_runner.execute",
            event_type="code_runner.execute_requested",
            operation_category="code_runner",
            resource_type="flow",
            resource_id=state.session_flow_id,
            extra_attributes={
                "platform.code_runner.language": self._language,
                "platform.code_runner.kind": kind,
                "platform.code_runner.entrypoint": entrypoint or "<first_function>",
                "platform.code_runner.service": runner_service,
                "platform.code_runner.path": runner_path,
                "platform.flow.branch_id": state.branch_id,
                "platform.flow.session_id": state.session_id,
                "platform.flow.task_id": state.task_id,
                "platform.flow.context_id": state.context_id,
            },
        ):
            raw_response = await self._client.post(
                runner_service,
                runner_path,
                json=request.model_dump(mode="json"),
                timeout=float(get_flows_settings().node_execution_wall_time_cap_seconds),
            )
        response = CodeExecutionResponse.model_validate(raw_response)
        if response.status == "failed":
            self._raise_execution_failed(response)
        self._apply_returned_state(state, response, frozen_snapshot)
        if response.status == "interrupted":
            self._raise_interrupted(response)
        return response

    async def _load_manifest(self) -> CapabilityManifest:
        raw_manifest = await self._client.get(
            "capability_gateway",
            CAPABILITY_MANIFEST_PATH,
            timeout=30.0,
        )
        return CapabilityManifest.model_validate(raw_manifest)

    def _execution_context(self, state: ExecutionState) -> CapabilityExecutionContext:
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError("Remote code execution requires Context with active_company")
        company_id = context.active_company.company_id
        user_id = context.user.user_id
        settings = get_flows_settings()
        log_context = get_log_context()
        request_id = log_context.get("request_id")
        request_id_value = request_id if isinstance(request_id, str) and request_id.strip() else None
        claims = CapabilityExecutionTokenClaims(
            company_id=company_id,
            user_id=user_id,
            flow_id=state.session_flow_id,
            branch_id=state.branch_id,
            session_id=state.session_id,
            task_id=state.task_id,
            context_id=state.context_id,
            request_id=request_id_value,
            exp=execution_token_exp(settings.capability_execution_token_ttl_seconds),
        )
        token = issue_execution_token(claims)
        return CapabilityExecutionContext(
            execution_token=token,
            company_id=company_id,
            user_id=user_id,
            flow_id=state.session_flow_id,
            branch_id=state.branch_id,
            session_id=state.session_id,
            task_id=state.task_id,
            context_id=state.context_id,
            request_id=request_id_value,
            trace_id=context.trace_id,
        )

    def _runner_endpoint(self) -> tuple[str, str]:
        endpoint = RUNNER_EXECUTE_PATHS.get(self._language)
        if endpoint is None:
            raise ValueError(f"Unsupported code runner language: {self._language}")
        return endpoint

    def _apply_returned_state(
        self,
        state: ExecutionState,
        response: CodeExecutionResponse,
        frozen_snapshot: dict[str, object],
    ) -> None:
        returned_state = ExecutionState.model_validate(response.state)
        assert_frozen_fields_unchanged(returned_state, frozen_snapshot)
        for field_name in returned_state.__class__.model_fields:
            setattr(state, field_name, getattr(returned_state, field_name))
        for field_name, field_value in (returned_state.model_extra or {}).items():
            setattr(state, field_name, field_value)

    def _raise_execution_failed(self, response: CodeExecutionResponse) -> None:
        error = response.error
        if error is None:
            raise CodeExecutionRuntimeError(
                language=self._language,
                service=self._runner_endpoint()[0],
                stage="unknown",
                message="Code runner returned failed status without error envelope",
                exception_type="CodeExecutionFailure",
            )
        logger.error(
            "code_runner.execution_failed",
            language=error.language,
            runner_service=error.service,
            stage=error.stage,
            exception_type=error.exception_type,
            request_id=error.request_id,
            trace_id=error.trace_id,
        )
        raise CodeExecutionRuntimeError(
            language=error.language,
            service=error.service,
            stage=error.stage,
            message=error.message,
            exception_type=error.exception_type,
            traceback=error.traceback,
            stdout=error.stdout,
            stderr=error.stderr,
            request_id=error.request_id,
            trace_id=error.trace_id,
        )

    def _raise_interrupted(self, response: CodeExecutionResponse) -> None:
        interrupt = response.interrupt
        if interrupt is None:
            raise CodeExecutionRuntimeError(
                language=self._language,
                service=self._runner_endpoint()[0],
                stage="interrupt",
                message="Code runner returned interrupted status without interrupt envelope",
                exception_type="CodeExecutionInterruptError",
            )
        raise FlowInterrupt(body=parse_interrupt_body_from_external_dict(interrupt.body))
