"""Remote code runner client для isolated code-runner сервисов."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import override

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.flow_ui.effects import apply_capability_platform_effects
from apps.flows.src.models.execution_limits import (
    get_node_execution_wall_time_cap_seconds,
    get_remote_code_runner_http_timeout_seconds,
)
from apps.flows.src.runners.base import BaseCodeRunner
from apps.flows.src.runners.capability_context import capability_execution_context
from apps.flows.src.runners.tool_context_view import build_tool_context_view
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.flow_interface_context import current_flow_interface
from apps.flows.src.state import (
    ExecutionState,
    parse_interrupt_body_from_external_dict,
    snapshot_frozen_fields,
)
from apps.flows.src.state.execution_state import ExecutionStateValue
from apps.flows.src.state.mutation_policy import (
    USER_RETURN_FORBIDDEN_FROZEN_FIELDS,
    should_skip_field_on_user_returned_state_copy,
)
from core.capabilities import (
    CODE_SANDBOX_FILESYSTEM_LIMIT_MB,
    CODE_SANDBOX_MEMORY_LIMIT_MB,
    CODE_SANDBOX_STDOUT_STDERR_LIMIT_BYTES,
    RUNNER_EXECUTE_PATHS,
    CapabilityExecutionContext,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionKind,
    CodeExecutionRequest,
    CodeExecutionResponse,
    CodeSandboxPolicy,
    CodeValidationRequest,
    CodeValidationResponse,
    filter_capabilities_by_allowed,
    locked_down_code_sandbox_policy,
    match_capability_language,
    runner_execute_endpoint,
    runner_validate_endpoint,
)
from core.capabilities.source_sanitize import reject_forbidden_platform_imports
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
    verify_execution_token,
)
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.errors import CodeExecutionRuntimeError, FrozenStateFieldError
from core.logging import get_log_context, get_logger
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue

CAPABILITY_MANIFEST_PATH = "/capability-gateway/api/v1/capabilities/manifest"
TOOL_RUNTIME_MANIFEST_PATH = "/flows/api/v1/tool-runtime/manifest"

logger = get_logger(__name__)


def _frozen_fields_differ(
    returned_state: ExecutionState,
    frozen_snapshot: dict[str, ExecutionStateValue],
    *,
    returned_keys: frozenset[str],
) -> list[str]:
    """Сравнивает только ключи, которые runner реально вернул в response.state."""
    state_fields = dict(vars(returned_state))
    changed_fields: list[str] = []
    for field_name, snapshot_value in frozen_snapshot.items():
        if field_name not in returned_keys:
            continue
        if state_fields.get(field_name) != snapshot_value:
            changed_fields.append(field_name)
    return changed_fields


def _restore_frozen_fields_from_snapshot(
    returned_state: ExecutionState,
    frozen_snapshot: dict[str, ExecutionStateValue],
) -> None:
    for field_name, snapshot_value in frozen_snapshot.items():
        returned_state[field_name] = deepcopy(snapshot_value)


def _merge_returned_state_fields(
    state: ExecutionState,
    returned_state: ExecutionState,
    *,
    returned_keys: frozenset[str],
) -> None:
    """Мержит только ключи из response.state — без дефолтов model_validate для отсутствующих полей."""
    for field_name in returned_state.__class__.model_fields:
        if field_name not in returned_keys:
            continue
        if should_skip_field_on_user_returned_state_copy(field_name):
            continue
        state[field_name] = returned_state[field_name]
    for field_name, field_value in returned_state.json_extra().items():
        if should_skip_field_on_user_returned_state_copy(field_name):
            continue
        state[field_name] = field_value


async def load_sandbox_capability_manifest(
    *,
    allowed_capabilities: list[str] | None = None,
) -> CapabilityManifest:
    """Merged manifest (gateway + flows tool-runtime), отфильтрованный по token grant."""
    client = ServiceClient()
    # Gateway без AuthMiddleware: только platform caps + builtins.
    # Company tools — с текущего flows context (signed headers), иначе
    # sandbox не видит только что созданный tool_repository row.
    # Таймаут = wall_time ноды: gateway/flows может быть занят длинным capability
    # (read_file, images.edit) — короткий таймаут убивал ноду до старта кода.
    manifest_timeout = float(get_node_execution_wall_time_cap_seconds())
    raw_gateway = await client.get(
        "capability_gateway",
        CAPABILITY_MANIFEST_PATH,
        timeout=manifest_timeout,
    )
    raw_tools = await client.get(
        "flows",
        TOOL_RUNTIME_MANIFEST_PATH,
        timeout=manifest_timeout,
    )
    gateway = CapabilityManifest.model_validate(raw_gateway)
    tools = CapabilityManifest.model_validate(raw_tools)
    by_name = {capability.name: capability for capability in gateway.capabilities}
    by_name.update({capability.name: capability for capability in tools.capabilities})
    manifest = CapabilityManifest(
        version=gateway.version,
        capabilities=[by_name[name] for name in sorted(by_name)],
    )
    return filter_capabilities_by_allowed(
        manifest,
        allowed_capabilities=allowed_capabilities,
    )


def apply_runner_returned_state(
    state: ExecutionState,
    response_state: JsonObject,
    *,
    frozen_snapshot: dict[str, ExecutionStateValue] | None = None,
) -> None:
    """Мержит response.state code-runner'а в ExecutionState с проверкой frozen-полей."""
    returned_keys = frozenset(response_state.keys())
    returned_state = ExecutionState.model_validate(response_state)
    snapshot = (
        frozen_snapshot if frozen_snapshot is not None else snapshot_frozen_fields(state)
    )
    changed_frozen = _frozen_fields_differ(
        returned_state,
        snapshot,
        returned_keys=returned_keys,
    )
    forbidden_changes = [
        field_name for field_name in changed_frozen if field_name in USER_RETURN_FORBIDDEN_FROZEN_FIELDS
    ]
    if forbidden_changes:
        raise FrozenStateFieldError(
            field=forbidden_changes[0],
            reason="assign",
        )
    if changed_frozen:
        logger.warning(
            "code_runner.returned_state_echoed_frozen_fields",
            changed_fields=changed_frozen,
        )
        _restore_frozen_fields_from_snapshot(returned_state, snapshot)
    _merge_returned_state_fields(
        state,
        returned_state,
        returned_keys=returned_keys,
    )


class RemoteCodeRunner(BaseCodeRunner):
    """BaseCodeRunner adapter over isolated code-runner HTTP services."""

    language: str = "remote"

    def __init__(self, language: str):
        known = match_capability_language(language)
        if known is None or known not in RUNNER_EXECUTE_PATHS:
            raise ValueError(f"Unsupported code runner language: {language}")
        self._language: CapabilityLanguage = known
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

    async def validate_remote(
        self,
        *,
        code: str,
        entrypoint: str | None,
        kind: CodeExecutionKind,
        flow_id: str | None = None,
        branch_id: str | None = None,
    ) -> CodeValidationResponse:
        runner_service, runner_path = self._runner_validation_endpoint()
        context = self._validation_context(flow_id=flow_id, branch_id=branch_id)
        claims = verify_execution_token(context.execution_token)
        manifest = await load_sandbox_capability_manifest(
            allowed_capabilities=claims.allowed_capabilities
        )
        request = CodeValidationRequest(
            kind=kind,
            language=self._language,
            code=reject_forbidden_platform_imports(code),
            entrypoint=entrypoint,
            wall_time_limit_seconds=get_flows_settings().node_execution_wall_time_cap_seconds,
            sandbox=self._sandbox_policy(),
            context=context,
            capability_manifest=manifest,
        )
        async with traced_operation(
            "flows.code_runner.validate",
            event_type="code_runner.validate_requested",
            operation_category="code_runner",
            resource_type="flow",
            resource_id=context.flow_id,
            extra_attributes={
                "platform.code_runner.language": self._language,
                "platform.code_runner.kind": kind,
                "platform.code_runner.entrypoint": entrypoint or "<first_function>",
                "platform.code_runner.service": runner_service,
                "platform.code_runner.path": runner_path,
                "platform.flow.branch_id": context.branch_id,
                "platform.flow.session_id": context.session_id,
                "platform.flow.task_id": context.task_id,
                "platform.flow.context_id": context.context_id,
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            raw_response = await self._client.post(
                runner_service,
                runner_path,
                json=request.model_dump(mode="json", exclude_none=True),
                timeout=get_remote_code_runner_http_timeout_seconds(),
            )
        return CodeValidationResponse.model_validate(raw_response)

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
        context = self._execution_context(state)
        claims = verify_execution_token(context.execution_token)
        manifest = await load_sandbox_capability_manifest(
            allowed_capabilities=claims.allowed_capabilities
        )
        request = CodeExecutionRequest(
            kind=kind,
            language=self._language,
            code=reject_forbidden_platform_imports(code),
            entrypoint=entrypoint,
            wall_time_limit_seconds=get_flows_settings().node_execution_wall_time_cap_seconds,
            sandbox=self._sandbox_policy(),
            args=args,
            state=build_tool_context_view(state),
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
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            raw_response = await self._client.post(
                runner_service,
                runner_path,
                json=request.model_dump(mode="json", exclude_none=True),
                timeout=get_remote_code_runner_http_timeout_seconds(),
            )
        response = CodeExecutionResponse.model_validate(raw_response)
        if response.status == "failed":
            self._raise_execution_failed(response)
        apply_runner_returned_state(state, response.state, frozen_snapshot=frozen_snapshot)
        if response.platform_effects:
            # UI-эффекты адресуют слоты и страницы интерфейса, поэтому допустимы
            # только внутри исполнения Flow; standalone-запуск tool без эффектов легален.
            apply_capability_platform_effects(
                state,
                response.platform_effects,
                context=context,
                manifest=manifest,
                interface=current_flow_interface(),
            )
        if response.status == "interrupted":
            self._raise_interrupted(response)
        return response

    def _sandbox_policy(self) -> CodeSandboxPolicy:
        wall_time_limit_seconds = get_flows_settings().node_execution_wall_time_cap_seconds
        return locked_down_code_sandbox_policy(
            wall_time_limit_seconds=wall_time_limit_seconds,
            cpu_time_limit_seconds=wall_time_limit_seconds,
            memory_limit_mb=CODE_SANDBOX_MEMORY_LIMIT_MB,
            filesystem_limit_mb=CODE_SANDBOX_FILESYSTEM_LIMIT_MB,
            stdout_stderr_limit_bytes=CODE_SANDBOX_STDOUT_STDERR_LIMIT_BYTES,
        )

    def _execution_context(self, state: ExecutionState) -> CapabilityExecutionContext:
        return capability_execution_context(state)

    def _validation_context(
        self,
        *,
        flow_id: str | None,
        branch_id: str | None,
    ) -> CapabilityExecutionContext:
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError("Remote code validation requires Context with active_company")
        company_id = context.active_company.company_id
        user_id = context.user.user_id
        settings = get_flows_settings()
        log_context = get_log_context()
        request_id = log_context.get("request_id")
        request_id_value = request_id if isinstance(request_id, str) and request_id.strip() else None
        flow_id_value = flow_id.strip() if isinstance(flow_id, str) and flow_id.strip() else "code-validation"
        branch_id_value = branch_id.strip() if isinstance(branch_id, str) and branch_id.strip() else "default"
        context_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        session_id = f"{flow_id_value}:validation:{context_id}"
        namespace_raw = (context.active_namespace or "").strip()
        namespace = namespace_raw if namespace_raw and namespace_raw != "default" else None
        claims = CapabilityExecutionTokenClaims(
            company_id=company_id,
            user_id=user_id,
            flow_id=flow_id_value,
            branch_id=branch_id_value,
            session_id=session_id,
            task_id=task_id,
            context_id=context_id,
            channel="code_validation",
            request_id=request_id_value,
            namespace=namespace,
            exp=execution_token_exp(settings.capability_execution_token_ttl_seconds),
        )
        token = issue_execution_token(claims)
        return CapabilityExecutionContext(
            execution_token=token,
            company_id=company_id,
            user_id=user_id,
            flow_id=flow_id_value,
            branch_id=branch_id_value,
            session_id=session_id,
            task_id=task_id,
            context_id=context_id,
            channel="code_validation",
            request_id=request_id_value,
            trace_id=context.trace_id,
            namespace=namespace,
        )

    def _runner_endpoint(self) -> tuple[str, str]:
        return runner_execute_endpoint(self._language)

    def _runner_validation_endpoint(self) -> tuple[str, str]:
        return runner_validate_endpoint(self._language)

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
        raise FlowInterrupt(
            body=parse_interrupt_body_from_external_dict(interrupt.body),
            correlation_id=uuid.UUID(interrupt.correlation_id)
            if interrupt.correlation_id is not None
            else None,
        )
