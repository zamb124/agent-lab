"""In-process unit-тесты статической логики code-runner executor-ов.

Code-runners запускаются как отдельные granian-процессы через ``make test-up``;
coverage собирается только в pytest-процессе, поэтому HTTP E2E-тесты в
``test_code_runner_services.py`` не инструментируют ``services/executor.py``.
Эти тесты импортируют executor-классы напрямую и вызывают pure-методы
(валидация source, верификация execution context, error-shaping) без subprocess.

Паттерн — как ``test_code_runner_security.py::test_go_static_guard_blocks_forbidden_import``.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from apps.code_runner_csharp.services.executor import CsharpSandboxExecutor
from apps.code_runner_go.services.executor import (
    FORBIDDEN_GO_IMPORTS,
    GoSandboxExecutor,
)
from apps.code_runner_node.services.executor import NodeSandboxExecutor
from apps.code_runner_python.services.executor import (
    PythonSandboxExecutor,
    _PythonWorker,
)
from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionRequest,
    CodeExecutionResponse,
    CodeSandboxPolicy,
    CodeValidationRequest,
    CodeValidationResponse,
    execution_token_exp,
    issue_execution_token,
    locked_down_code_sandbox_policy,
)


class _SandboxExecutor(Protocol):
    """Контракт static-security gate всех code-runner executor-ов."""

    def _verify_execution_request(
        self,
        request: CodeExecutionRequest,
    ) -> CodeExecutionResponse | None: ...

    def _verify_validation_request(
        self,
        request: CodeValidationRequest,
    ) -> CodeValidationResponse | None: ...


def _sandbox_policy(wall_time_limit_seconds: int) -> CodeSandboxPolicy:
    return locked_down_code_sandbox_policy(
        wall_time_limit_seconds=wall_time_limit_seconds,
        cpu_time_limit_seconds=wall_time_limit_seconds,
        memory_limit_mb=256,
        filesystem_limit_mb=64,
        stdout_stderr_limit_bytes=1_048_576,
    )


def _claims() -> CapabilityExecutionTokenClaims:
    return CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="executor_unit_user",
        flow_id="executor_unit_flow",
        branch_id="main",
        session_id="executor_unit_flow:executor_unit_ctx",
        task_id="executor_unit_task",
        context_id="executor_unit_ctx",
        channel="a2a",
        request_id="executor-unit-request-id",
        exp=execution_token_exp(300),
    )


def _signed_context() -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(_claims()),
        company_id="system",
        user_id="executor_unit_user",
        flow_id="executor_unit_flow",
        branch_id="main",
        session_id="executor_unit_flow:executor_unit_ctx",
        task_id="executor_unit_task",
        context_id="executor_unit_ctx",
        channel="a2a",
        request_id="executor-unit-request-id",
        trace_id="executor-unit-trace-id",
    )


def _tampered_context() -> CapabilityExecutionContext:
    """Context где company_id не совпадает с claims в token — verify_execution_context падает."""
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(_claims()),
        company_id="attacker-company",
        user_id="executor_unit_user",
        flow_id="executor_unit_flow",
        branch_id="main",
        session_id="executor_unit_flow:executor_unit_ctx",
        task_id="executor_unit_task",
        context_id="executor_unit_ctx",
        channel="a2a",
        request_id="executor-unit-request-id",
        trace_id="executor-unit-trace-id",
    )


def _execution_request(
    language: CapabilityLanguage,
    code: str,
    *,
    context: CapabilityExecutionContext | None = None,
) -> CodeExecutionRequest:
    return CodeExecutionRequest(
        kind="node",
        language=language,
        code=code,
        entrypoint=None,
        wall_time_limit_seconds=30,
        sandbox=_sandbox_policy(30),
        args={},
        state={},
        context=context or _signed_context(),
        capability_manifest=CapabilityManifest(version="unit-test", capabilities=[]),
    )


def _validation_request(
    language: CapabilityLanguage,
    code: str,
    *,
    context: CapabilityExecutionContext | None = None,
) -> CodeValidationRequest:
    return CodeValidationRequest(
        kind="node",
        language=language,
        code=code,
        entrypoint=None,
        wall_time_limit_seconds=30,
        sandbox=_sandbox_policy(30),
        context=context or _signed_context(),
        capability_manifest=CapabilityManifest(version="unit-test", capabilities=[]),
    )


# --- Go static source guard -------------------------------------------------


class TestGoStaticSourceGuard:
    """``GoSandboxExecutor._validate_user_source`` — pure-валидатор импортов."""

    def test_blocks_every_forbidden_top_level_import(self) -> None:
        executor = GoSandboxExecutor()
        for forbidden in sorted(FORBIDDEN_GO_IMPORTS):
            source = (
                "package main\n\n"
                f'import "{forbidden}"\n\n'
                "func Run(args map[string]any, state map[string]any) (any, error) {\n"
                "    return nil, nil\n"
                "}\n"
            )
            with pytest.raises(PermissionError, match="not allowed"):
                executor._validate_user_source(source)

    def test_blocks_forbidden_subpath_import_root(self) -> None:
        executor = GoSandboxExecutor()
        source = (
            "package main\n\n"
            'import "os/exec"\n\n'
            "func Run(args map[string]any, state map[string]any) (any, error) {\n"
            "    return nil, nil\n"
            "}\n"
        )
        with pytest.raises(PermissionError, match="os"):
            executor._validate_user_source(source)

    def test_allows_safe_imports(self) -> None:
        executor = GoSandboxExecutor()
        source = (
            "package main\n\n"
            'import "strings"\n\n'
            "func Run(args map[string]any, state map[string]any) (any, error) {\n"
            '    return strings.ToUpper("ok"), nil\n'
            "}\n"
        )
        executor._validate_user_source(source)

    def test_blocks_stdlib_outside_allowlist(self) -> None:
        executor = GoSandboxExecutor()
        source = (
            "package main\n\n"
            'import "net/http"\n\n'
            "func Run(args map[string]any, state map[string]any) (any, error) {\n"
            "    return nil, nil\n"
            "}\n"
        )
        with pytest.raises(PermissionError, match="net/http"):
            executor._validate_user_source(source)

    def test_go_imports_parses_single_and_multi_line(self) -> None:
        executor = GoSandboxExecutor()
        single = 'package main\nimport "fmt"\n'
        multi = (
            "package main\nimport (\n"
            '  "fmt"\n'
            '  "strings"\n'
            ")\n"
        )
        assert executor._go_imports(single) == ["fmt"]
        assert executor._go_imports(multi) == ["fmt", "strings"]

    def test_go_imports_returns_empty_when_no_imports(self) -> None:
        executor = GoSandboxExecutor()
        assert executor._go_imports("package main\n") == []


# --- C# static source guard -------------------------------------------------


class TestCsharpStaticSourceGuard:
    """``CsharpSandboxExecutor._validate_user_source`` — using + forbidden patterns."""

    def test_rejects_disallowed_namespace(self) -> None:
        executor = CsharpSandboxExecutor()
        source = (
            "using System.Net.Http;\n\n"
            "object? Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    return null;\n"
            "}\n"
        )
        with pytest.raises(PermissionError, match="System.Net.Http"):
            executor._validate_user_source(source)

    def test_allows_whitelisted_usings(self) -> None:
        executor = CsharpSandboxExecutor()
        source = (
            "using System;\n"
            "using System.Collections.Generic;\n"
            "using System.Linq;\n"
            "using System.Text.RegularExpressions;\n"
            "using System.Threading.Tasks;\n\n"
            "object? Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    return args.Count;\n"
            "}\n"
        )
        executor._validate_user_source(source)

    def test_rejects_forbidden_pattern_in_body(self) -> None:
        executor = CsharpSandboxExecutor()
        source = (
            "using System.Collections.Generic;\n\n"
            "object? Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            '    return System.Diagnostics.Process.Start("ls");\n'
            "}\n"
        )
        with pytest.raises(PermissionError, match="Diagnostics"):
            executor._validate_user_source(source)

    def test_rejects_reflection_pattern(self) -> None:
        executor = CsharpSandboxExecutor()
        source = (
            "using System.Collections.Generic;\n\n"
            "object? Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    return System.Reflection.Assembly.Load(new byte[0]);\n"
            "}\n"
        )
        with pytest.raises(PermissionError, match="Reflection"):
            executor._validate_user_source(source)


# --- Execution context verification (all four executors) -------------------


@pytest.fixture(params=["python", "node", "go", "csharp"])
def executor(request: pytest.FixtureRequest) -> _SandboxExecutor:
    """Параметризованный executor по имени."""
    name = request.param
    if name == "python":
        return PythonSandboxExecutor()
    if name == "node":
        return NodeSandboxExecutor()
    if name == "go":
        return GoSandboxExecutor()
    if name == "csharp":
        return CsharpSandboxExecutor()
    raise ValueError(f"unknown executor: {name}")


class TestExecutionContextVerification:
    """``_verify_execution_request`` / ``_verify_validation_request`` — security gate."""

    def test_verify_execution_request_returns_failed_on_company_mismatch(
        self,
        executor: _SandboxExecutor,
    ) -> None:
        request = _execution_request("python", "x = 1\n", context=_tampered_context())
        result = executor._verify_execution_request(request)
        assert result is not None
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.stage == "security"

    def test_verify_validation_request_returns_failed_on_company_mismatch(
        self,
        executor: _SandboxExecutor,
    ) -> None:
        request = _validation_request("python", "x = 1\n", context=_tampered_context())
        result = executor._verify_validation_request(request)
        assert result is not None
        assert result.valid is False
        assert result.error is not None
        assert result.error.stage == "security"

    def test_verify_execution_request_returns_none_for_signed_context(
        self,
        executor: _SandboxExecutor,
    ) -> None:
        request = _execution_request("python", "x = 1\n")
        result = executor._verify_execution_request(request)
        assert result is None

    def test_verify_validation_request_returns_none_for_signed_context(
        self,
        executor: _SandboxExecutor,
    ) -> None:
        request = _validation_request("python", "x = 1\n")
        result = executor._verify_validation_request(request)
        assert result is None


# --- Python executor specifics ---------------------------------------------


class TestPythonExecutorInProcess:
    """Pure-логика ``PythonSandboxExecutor`` без subprocess."""

    def test_worker_source_contains_sandbox_imports(self) -> None:
        executor = PythonSandboxExecutor()
        source = executor._worker_source()
        assert "import ast" in source
        assert "import json" in source
        assert "import traceback" in source
        assert "capability_call_path" in source

    def test_worker_source_compiles_to_valid_python(self) -> None:
        executor = PythonSandboxExecutor()
        source = executor._worker_source()
        _ = compile(source, "<python_worker_source>", "exec")

    def test_worker_source_forwards_traceparent_to_gateway(self) -> None:
        executor = PythonSandboxExecutor()
        source = executor._worker_source()
        assert 'current_request.get("traceparent")' in source
        assert 'headers["traceparent"]' in source

    @staticmethod
    def _worker_with_fake_process(
        response: CodeExecutionResponse,
    ) -> tuple[_PythonWorker, bytearray]:
        from asyncio.subprocess import Process
        from pathlib import Path
        from typing import cast

        class _FakeStdin:
            buffer: bytearray

            def __init__(self) -> None:
                self.buffer = bytearray()

            def write(self, data: bytes) -> None:
                self.buffer.extend(data)

            async def drain(self) -> None:
                pass

        class _FakeStdout:
            _line: bytes

            def __init__(self, line: bytes) -> None:
                self._line = line

            async def readline(self) -> bytes:
                return self._line

        class _FakeProcess:
            returncode: int | None
            stdin: _FakeStdin
            stdout: _FakeStdout

            def __init__(self, line: bytes) -> None:
                self.returncode = None
                self.stdin = _FakeStdin()
                self.stdout = _FakeStdout(line)

        process = _FakeProcess(response.model_dump_json().encode("utf-8") + b"\n")
        written = process.stdin.buffer
        worker = _PythonWorker(
            worker_path=Path("worker.py"),
            gateway_url="http://localhost/capability-gateway",
            sandbox_site=Path("sandbox-site"),
        )
        worker._process = cast(Process, cast(object, process))
        return worker, written

    def test_invoke_injects_traceparent_into_ipc_payload(self) -> None:
        import asyncio
        import json

        worker, written = self._worker_with_fake_process(
            CodeExecutionResponse(status="completed", result={"ok": True})
        )
        request = _execution_request("python", "async def run(args, state):\n    return args\n")
        traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        response = asyncio.run(worker.invoke(request, traceparent=traceparent))

        payload = json.loads(written.decode("utf-8"))
        assert payload["traceparent"] == traceparent
        assert response.status == "completed"

    def test_invoke_omits_traceparent_when_not_provided(self) -> None:
        import asyncio
        import json

        worker, written = self._worker_with_fake_process(CodeExecutionResponse(status="completed"))
        request = _execution_request("python", "async def run(args, state):\n    return args\n")
        _ = asyncio.run(worker.invoke(request))

        payload = json.loads(written.decode("utf-8"))
        assert "traceparent" not in payload

    def test_execute_rejects_wrong_language_without_worker(self) -> None:
        import asyncio

        executor = PythonSandboxExecutor()
        request = _execution_request("go", "package main\n")
        response = asyncio.run(executor.execute(request))
        assert response.status == "failed"
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"

    def test_validate_rejects_wrong_language_without_worker(self) -> None:
        import asyncio

        executor = PythonSandboxExecutor()
        request = _validation_request("go", "package main\n")
        response = asyncio.run(executor.validate(request))
        assert response.valid is False
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"


# --- Node executor specifics ------------------------------------------------


class TestNodeExecutorInProcess:
    """Pure-логика ``NodeSandboxExecutor`` без subprocess."""

    def test_execute_rejects_wrong_language_without_worker(self) -> None:
        import asyncio

        executor = NodeSandboxExecutor()
        request = _execution_request("python", "x = 1\n")
        response = asyncio.run(executor.execute(request))
        assert response.status == "failed"
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"

    def test_validate_rejects_wrong_language_without_worker(self) -> None:
        import asyncio

        executor = NodeSandboxExecutor()
        request = _validation_request("python", "x = 1\n")
        response = asyncio.run(executor.validate(request))
        assert response.valid is False
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"


# --- Go executor specifics --------------------------------------------------


class TestGoExecutorInProcess:
    """Pure-логика ``GoSandboxExecutor`` без subprocess."""

    def test_execute_rejects_wrong_language_without_build(self) -> None:
        import asyncio

        executor = GoSandboxExecutor()
        request = _execution_request("python", "x = 1\n")
        response = asyncio.run(executor.execute(request))
        assert response.status == "failed"
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"

    def test_validate_rejects_wrong_language_without_build(self) -> None:
        import asyncio

        executor = GoSandboxExecutor()
        request = _validation_request("python", "x = 1\n")
        response = asyncio.run(executor.validate(request))
        assert response.valid is False
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"


# --- C# executor specifics --------------------------------------------------


class TestCsharpExecutorInProcess:
    """Pure-логика ``CsharpSandboxExecutor`` без subprocess."""

    def test_execute_rejects_wrong_language_without_build(self) -> None:
        import asyncio

        executor = CsharpSandboxExecutor()
        request = _execution_request("python", "x = 1\n")
        response = asyncio.run(executor.execute(request))
        assert response.status == "failed"
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"

    def test_validate_rejects_wrong_language_without_build(self) -> None:
        import asyncio

        executor = CsharpSandboxExecutor()
        request = _validation_request("python", "x = 1\n")
        response = asyncio.run(executor.validate(request))
        assert response.valid is False
        assert response.error is not None
        assert response.error.stage == "validation"
        assert response.error.exception_type == "UnsupportedLanguageError"
