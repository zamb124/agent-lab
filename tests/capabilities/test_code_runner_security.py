"""Strict sandbox security contract tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.code_runner_csharp.services.executor import CsharpSandboxExecutor
from apps.code_runner_go.services.executor import GoSandboxExecutor
from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionRequest,
    CodeSandboxFilesystemPolicy,
    CodeSandboxNetworkPolicy,
    CodeSandboxPolicy,
    CodeSandboxResourceLimits,
    CodeValidationRequest,
    execution_token_exp,
    issue_execution_token,
    locked_down_code_sandbox_policy,
)

pytestmark = pytest.mark.timeout(180)


def _sandbox_policy(wall_time_limit_seconds: int) -> CodeSandboxPolicy:
    return locked_down_code_sandbox_policy(
        wall_time_limit_seconds=wall_time_limit_seconds,
        cpu_time_limit_seconds=wall_time_limit_seconds,
        memory_limit_mb=256,
        filesystem_limit_mb=64,
        stdout_stderr_limit_bytes=1_048_576,
    )


def _execution_context(execution_token: str) -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        execution_token=execution_token,
        company_id="system",
        user_id="security_test_user",
        flow_id="security_test_flow",
        branch_id="main",
        session_id="security_test_flow:security_context",
        task_id="security_task",
        context_id="security_context",
        channel="a2a",
        request_id="security-request-id",
        trace_id="security-trace-id",
    )


def _signed_context() -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="security_test_user",
        flow_id="security_test_flow",
        branch_id="main",
        session_id="security_test_flow:security_context",
        task_id="security_task",
        context_id="security_context",
        channel="a2a",
        request_id="security-request-id",
        exp=execution_token_exp(300),
    )
    return _execution_context(issue_execution_token(claims))


def _execution_request(language: CapabilityLanguage, code: str) -> dict[str, object]:
    wall_time_limit_seconds = 30
    request = CodeExecutionRequest(
        kind="node",
        language=language,
        code=code,
        entrypoint=None,
        wall_time_limit_seconds=wall_time_limit_seconds,
        sandbox=_sandbox_policy(wall_time_limit_seconds),
        args={},
        state={},
        context=_signed_context(),
        capability_manifest=CapabilityManifest(version="security-test", capabilities=[]),
    )
    return request.model_dump(mode="json")


def _validation_request(language: CapabilityLanguage, code: str) -> dict[str, object]:
    wall_time_limit_seconds = 30
    request = CodeValidationRequest(
        kind="node",
        language=language,
        code=code,
        entrypoint=None,
        wall_time_limit_seconds=wall_time_limit_seconds,
        sandbox=_sandbox_policy(wall_time_limit_seconds),
        context=_signed_context(),
        capability_manifest=CapabilityManifest(version="security-test", capabilities=[]),
    )
    return request.model_dump(mode="json")


def test_sandbox_policy_rejects_dynamic_code() -> None:
    with pytest.raises(ValueError, match="allow_dynamic_code"):
        CodeSandboxPolicy(
            profile="locked_down_v1",
            limits=CodeSandboxResourceLimits(
                wall_time_limit_seconds=30,
                cpu_time_limit_seconds=30,
                memory_limit_mb=256,
                filesystem_limit_mb=64,
                stdout_stderr_limit_bytes=1_048_576,
            ),
            network=CodeSandboxNetworkPolicy(
                mode="capability_gateway_only",
                allowed_services=["capability_gateway"],
            ),
            filesystem=CodeSandboxFilesystemPolicy(
                mode="ephemeral_workspace",
                read_only_root=True,
                writable_tmp=True,
            ),
            allow_dynamic_code=True,
            allow_reflection=False,
        )


def test_execution_request_requires_sandbox_wall_time_match() -> None:
    with pytest.raises(ValueError, match="wall_time_limit_seconds"):
        CodeExecutionRequest(
            kind="node",
            language="python",
            code="async def run(args, state):\n    return None\n",
            entrypoint=None,
            wall_time_limit_seconds=10,
            sandbox=_sandbox_policy(30),
            args={},
            state={},
            context=_signed_context(),
            capability_manifest=CapabilityManifest(version="security-test", capabilities=[]),
        )


def test_go_static_guard_blocks_forbidden_import() -> None:
    with pytest.raises(PermissionError, match="os"):
        GoSandboxExecutor()._validate_user_source(
            'package main\n\nimport "os"\n\n'
            "func Run(args map[string]any, state map[string]any) (any, error) {\n"
            "    return os.Environ(), nil\n"
            "}\n"
        )


def test_csharp_static_guard_blocks_forbidden_api() -> None:
    with pytest.raises(PermissionError, match="System.IO"):
        CsharpSandboxExecutor()._validate_user_source(
            "using System.Collections.Generic;\n"
            "using System.IO;\n\n"
            "object? Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            '    return File.ReadAllText("/etc/passwd");\n'
            "}\n"
        )


@pytest.mark.asyncio
async def test_python_runner_rejects_invalid_execution_token(sandbox_services) -> None:
    payload = _execution_request(
        "python",
        "async def run(args, state):\n"
        "    state['executed'] = True\n"
        "    return {'ok': True}\n",
    )
    context = payload["context"]
    assert isinstance(context, dict)
    context["execution_token"] = "invalid.token"

    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_python']}/code-runner-python/api/v1/execute",
            json=payload,
            headers={"X-Request-Id": "security-request-id", "X-Trace-Id": "security-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["stage"] == "security"
    assert body["error"]["request_id"] == "security-request-id"
    assert body["error"]["trace_id"] == "security-trace-id"


@pytest.mark.asyncio
async def test_python_runner_blocks_dangerous_builtin(sandbox_services) -> None:
    payload = _execution_request(
        "python",
        "async def run(args, state):\n"
        "    return eval('1 + 1')\n",
    )

    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_python']}/code-runner-python/api/v1/execute",
            json=payload,
            headers={"X-Request-Id": "security-request-id", "X-Trace-Id": "security-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "failed"
    assert "builtin is not allowed" in body["error"]["message"]
    assert body["error"]["exception_type"] == "SandboxPolicyViolation"


@pytest.mark.asyncio
async def test_python_runner_blocks_forbidden_import(sandbox_services) -> None:
    payload = _validation_request(
        "python",
        "import os\n\n"
        "async def run(args, state):\n"
        "    return os.environ\n",
    )

    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_python']}/code-runner-python/api/v1/validate",
            json=payload,
            headers={"X-Request-Id": "security-request-id", "X-Trace-Id": "security-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["valid"] is False
    assert "import is not allowed" in body["error"]["message"]
    assert body["error"]["exception_type"] == "SandboxPolicyViolation"


@pytest.mark.asyncio
async def test_python_runner_rejects_hidden_capability_not_in_manifest(
    sandbox_services,
) -> None:
    payload = _execution_request(
        "python",
        "async def run(args, state):\n"
        "    return await capability('files.create', content='x', original_name='x.txt')\n",
    )

    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_python']}/code-runner-python/api/v1/execute",
            json=payload,
            headers={"X-Request-Id": "security-request-id", "X-Trace-Id": "security-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "failed"
    assert "not declared in manifest" in body["error"]["message"]
    assert body["error"]["exception_type"] == "SandboxPolicyViolation"
