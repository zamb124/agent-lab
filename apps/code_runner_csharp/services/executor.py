"""C# sandbox executor по контракту CodeExecutionRequest."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
import textwrap
import traceback
from pathlib import Path

from core.capabilities import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    CodeValidationRequest,
    CodeValidationResponse,
    code_execution_failed_response,
    code_validation_failed_response,
    verify_execution_context,
)
from core.capabilities.runtime_executables import (
    resolve_runtime_executable,
    runtime_executable_required_message,
)
from core.config import get_settings
from core.tracing.operation_span import traced_operation

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"
RESPONSE_PREFIX = "__CODE_RUNNER_RESPONSE__"
SERVICE_NAME = "code_runner_csharp"
DOTNET_BIN_ENV = "CODE_RUNNER_DOTNET_BIN"
CSHARP_METHOD_RE = re.compile(
    r"(?m)^\s*"
    + r"(?:(?:public|private|protected|internal|static|async|virtual|override|sealed|new|partial)\s+)*"
    + r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]\.?]*\s+)+"
    + r"([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
ALLOWED_CSHARP_USINGS: frozenset[str] = frozenset(
    {
        "System",
        "System.Collections.Generic",
        "System.Linq",
        "System.Threading.Tasks",
    }
)
FORBIDDEN_CSHARP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bSystem\.IO\b"),
    re.compile(r"\bSystem\.Net\b"),
    re.compile(r"\bSystem\.Reflection\b"),
    re.compile(r"\bSystem\.Diagnostics\b"),
    re.compile(r"\bSystem\.Runtime\.InteropServices\b"),
    re.compile(r"\bDllImport\b"),
    re.compile(r"\bProcess\b"),
    re.compile(r"\bFile\b"),
    re.compile(r"\bDirectory\b"),
    re.compile(r"\bEnvironment\b"),
    re.compile(r"\bAssembly\b"),
    re.compile(r"\bActivator\b"),
    re.compile(r"\bType\.GetType\b"),
    re.compile(r"\bHttpClient\b"),
    re.compile(r"\bSocket\b"),
)


class CsharpSandboxExecutor:
    """Исполняет C# user code через cached .NET build artifact."""

    def __init__(self) -> None:
        self._artifact_root: Path = Path(tempfile.mkdtemp(prefix="code-runner-csharp-artifacts-"))
        self._build_locks: dict[str, asyncio.Lock] = {}
        self._build_locks_guard: asyncio.Lock = asyncio.Lock()

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        security_error = self._verify_execution_request(request)
        if security_error is not None:
            return security_error
        if request.language != "csharp":
            return self._failed_response(
                request=request,
                stage="validation",
                message=f"code-runner-csharp cannot execute language={request.language}",
                exception_type="UnsupportedLanguageError",
            )
        try:
            self._validate_user_source(request.code)
        except Exception as exc:
            return self._failed_response(
                request=request,
                stage="security",
                message=str(exc),
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )

        dotnet_bin = resolve_runtime_executable("dotnet", override_env=DOTNET_BIN_ENV)
        if dotnet_bin is None:
            return self._failed_response(
                request=request,
                stage="runtime",
                message=runtime_executable_required_message("dotnet", override_env=DOTNET_BIN_ENV),
                exception_type="MissingRuntimeExecutableError",
            )

        gateway_url = get_settings().server.get_service_url("capability_gateway")
        async with traced_operation(
            "code_runner_csharp.execute",
            event_type="code_runner.execute",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": request.entrypoint or "<first_function>",
                "platform.code_runner.runtime": "build_artifact_cache",
                "platform.code_runner.dotnet_target": "net10.0",
                "platform.code_runner.csharp_lang_version": "14.0",
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            artifact_key = self._artifact_key(request)
            artifact_path = self._artifact_root / artifact_key
            output_path = artifact_path / "out"
            dll_path = output_path / "Sandbox.dll"
            try:
                await self._ensure_artifact(
                    request=request,
                    dotnet_bin=dotnet_bin,
                    artifact_path=artifact_path,
                    output_path=output_path,
                    dll_path=dll_path,
                )
            except Exception as exc:
                return self._failed_response(
                    request=request,
                    stage="compile",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            with tempfile.TemporaryDirectory(prefix="code-runner-csharp-call-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                request_path = tmp_path / "request.json"
                _ = request_path.write_text(request.model_dump_json(), encoding="utf-8")
                completed = await self._run_dotnet(
                    request=request,
                    dotnet_bin=dotnet_bin,
                    dll_path=dll_path,
                    request_path=request_path,
                    gateway_url=gateway_url,
                    wall_time_limit_seconds=request.wall_time_limit_seconds,
                )
        return completed

    async def validate(self, request: CodeValidationRequest) -> CodeValidationResponse:
        security_error = self._verify_validation_request(request)
        if security_error is not None:
            return security_error
        if request.language != "csharp":
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message=f"code-runner-csharp cannot validate language={request.language}",
                exception_type="UnsupportedLanguageError",
            )
        try:
            self._validate_user_source(request.code)
        except Exception as exc:
            return self._failed_validation_response(
                request=request,
                stage="security",
                message=str(exc),
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )

        entrypoint = request.entrypoint.strip() if isinstance(request.entrypoint, str) and request.entrypoint.strip() else self._infer_entrypoint(request.code)
        if entrypoint is None:
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message="Entrypoint function not found: declare at least one function",
                exception_type="EntrypointNotFoundError",
            )
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint) is None:
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message=f"invalid C# entrypoint name: {entrypoint!r}",
                exception_type="InvalidEntrypointError",
            )
        if entrypoint not in self._method_names(request.code):
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message=f"Entrypoint function not found: {entrypoint}",
                exception_type="EntrypointNotFoundError",
            )

        dotnet_bin = resolve_runtime_executable("dotnet", override_env=DOTNET_BIN_ENV)
        if dotnet_bin is None:
            return self._failed_validation_response(
                request=request,
                stage="runtime",
                message=runtime_executable_required_message("dotnet", override_env=DOTNET_BIN_ENV),
                exception_type="MissingRuntimeExecutableError",
            )

        async with traced_operation(
            "code_runner_csharp.validate",
            event_type="code_runner.validate",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": entrypoint,
                "platform.code_runner.runtime": "build_artifact_cache",
                "platform.code_runner.dotnet_target": "net10.0",
                "platform.code_runner.csharp_lang_version": "14.0",
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            request_for_build = request.model_copy(update={"entrypoint": entrypoint})
            artifact_key = self._artifact_key(request_for_build)
            artifact_path = self._artifact_root / artifact_key
            output_path = artifact_path / "out"
            dll_path = output_path / "Sandbox.dll"
            try:
                await self._ensure_artifact(
                    request=request_for_build,
                    dotnet_bin=dotnet_bin,
                    artifact_path=artifact_path,
                    output_path=output_path,
                    dll_path=dll_path,
                )
            except Exception as exc:
                return self._failed_validation_response(
                    request=request,
                    stage="compile",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
        return CodeValidationResponse(valid=True)

    def _artifact_key(self, request: CodeExecutionRequest | CodeValidationRequest) -> str:
        payload = {
            "language": request.language,
            "code": request.code,
            "entrypoint": request.entrypoint,
            "capability_manifest": request.capability_manifest.model_dump(mode="json"),
            "target": "net10.0",
            "lang_version": "14.0",
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _build_lock(self, artifact_key: str) -> asyncio.Lock:
        async with self._build_locks_guard:
            lock = self._build_locks.get(artifact_key)
            if lock is None:
                lock = asyncio.Lock()
                self._build_locks[artifact_key] = lock
            return lock

    async def _ensure_artifact(
        self,
        *,
        request: CodeExecutionRequest | CodeValidationRequest,
        dotnet_bin: str,
        artifact_path: Path,
        output_path: Path,
        dll_path: Path,
    ) -> None:
        if dll_path.exists():
            return
        lock = await self._build_lock(artifact_path.name)
        async with lock:
            if dll_path.exists():
                return
            artifact_path.mkdir(parents=True, exist_ok=True)
            output_path.mkdir(parents=True, exist_ok=True)
            project_path = artifact_path / "Sandbox.csproj"
            runner_path = artifact_path / "Runner.cs"
            user_path = artifact_path / "UserCode.cs"
            sdk_path = artifact_path / "Sdk.cs"
            entrypoint_check_path = artifact_path / "EntrypointCheck.cs"
            _ = project_path.write_text(self._project_source(), encoding="utf-8")
            _ = runner_path.write_text(self._runner_source(), encoding="utf-8")
            _ = user_path.write_text(self._user_source(request.code), encoding="utf-8")
            _ = sdk_path.write_text(self._sdk_source(request), encoding="utf-8")
            entrypoint = request.entrypoint.strip() if isinstance(request.entrypoint, str) and request.entrypoint.strip() else ""
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint) is not None:
                _ = entrypoint_check_path.write_text(
                    self._entrypoint_check_source(entrypoint), encoding="utf-8"
                )
            env = self._dotnet_env()
            process = await asyncio.create_subprocess_exec(
                dotnet_bin,
                "build",
                str(project_path),
                "-c",
                "Release",
                "-o",
                str(output_path),
                "--nologo",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    "csharp artifact build failed: "
                    + stdout.decode("utf-8", errors="replace")
                    + stderr.decode("utf-8", errors="replace")
                )
            if not dll_path.exists():
                raise RuntimeError(f"csharp artifact build did not produce {dll_path}")

    async def _run_dotnet(
        self,
        *,
        request: CodeExecutionRequest,
        dotnet_bin: str,
        dll_path: Path,
        request_path: Path,
        gateway_url: str,
        wall_time_limit_seconds: int,
    ) -> CodeExecutionResponse:
        env = self._dotnet_env()
        process = await asyncio.create_subprocess_exec(
            dotnet_bin,
            str(dll_path),
            str(request_path),
            gateway_url,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=float(wall_time_limit_seconds),
            )
        except TimeoutError as exc:
            _ = process.kill()
            _ = await process.wait()
            return self._failed_response(
                request=request,
                stage="timeout",
                message="csharp sandbox exceeded wall time limit",
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            return self._failed_response(
                request=request,
                stage="process",
                message=f"csharp sandbox process exited with code {process.returncode}",
                exception_type="CsharpSandboxProcessError",
                stdout=stdout_text,
                stderr=stderr_text,
            )

        try:
            response_line = self._extract_response_line(stdout_text)
            response = CodeExecutionResponse.model_validate_json(response_line)
        except Exception as exc:
            return self._failed_response(
                request=request,
                stage="response_parse",
                message=str(exc),
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
                stdout=stdout_text,
                stderr=stderr_text,
            )
        if response.status == "failed" and response.error is not None:
            response.error.stdout = stdout_text
            response.error.stderr = stderr_text
        return response

    def _dotnet_env(self) -> dict[str, str]:
        return {
            **os.environ,
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        }

    def _extract_response_line(self, stdout_text: str) -> str:
        for line in reversed(stdout_text.splitlines()):
            if line.startswith(RESPONSE_PREFIX):
                return line.removeprefix(RESPONSE_PREFIX)
        raise RuntimeError("csharp sandbox did not return execution response")

    def _failed_response(
        self,
        *,
        request: CodeExecutionRequest,
        stage: str,
        message: str,
        exception_type: str,
        traceback_text: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> CodeExecutionResponse:
        return code_execution_failed_response(
            request,
            service=SERVICE_NAME,
            stage=stage,
            message=message,
            exception_type=exception_type,
            traceback_text=traceback_text,
            stdout=stdout,
            stderr=stderr,
        )

    def _failed_validation_response(
        self,
        *,
        request: CodeValidationRequest,
        stage: str,
        message: str,
        exception_type: str,
        traceback_text: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> CodeValidationResponse:
        return code_validation_failed_response(
            request,
            service=SERVICE_NAME,
            stage=stage,
            message=message,
            exception_type=exception_type,
            traceback_text=traceback_text,
            stdout=stdout,
            stderr=stderr,
        )

    def _verify_execution_request(
        self,
        request: CodeExecutionRequest,
    ) -> CodeExecutionResponse | None:
        try:
            verify_execution_context(request.context)
        except Exception as exc:
            return self._failed_response(
                request=request,
                stage="security",
                message=str(exc),
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )
        return None

    def _verify_validation_request(
        self,
        request: CodeValidationRequest,
    ) -> CodeValidationResponse | None:
        try:
            verify_execution_context(request.context)
        except Exception as exc:
            return self._failed_validation_response(
                request=request,
                stage="security",
                message=str(exc),
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )
        return None

    def _validate_user_source(self, code: str) -> None:
        for match in re.finditer(r"(?m)^\s*using\s+([^;]+);", code):
            namespace = match.group(1).strip()
            if namespace not in ALLOWED_CSHARP_USINGS:
                raise PermissionError(f"csharp using is not allowed in code runner: {namespace}")
        for pattern in FORBIDDEN_CSHARP_PATTERNS:
            if pattern.search(code):
                raise PermissionError(
                    f"csharp API is not allowed in code runner: {pattern.pattern}"
                )

    def _infer_entrypoint(self, code: str) -> str | None:
        match = CSHARP_METHOD_RE.search(code)
        return match.group(1) if match else None

    def _method_names(self, code: str) -> set[str]:
        return {match.group(1) for match in CSHARP_METHOD_RE.finditer(code)}

    def _project_source(self) -> str:
        return textwrap.dedent(
            """
            <Project Sdk="Microsoft.NET.Sdk">
              <PropertyGroup>
                <OutputType>Exe</OutputType>
                <TargetFramework>net10.0</TargetFramework>
                <LangVersion>14.0</LangVersion>
                <Nullable>enable</Nullable>
                <ImplicitUsings>disable</ImplicitUsings>
              </PropertyGroup>
            </Project>
            """
        ).strip()

    def _user_source(self, source: str) -> str:
        if re.search(r"\b(class|record|struct)\b", source):
            return source
        using_pattern = re.compile(r"(?m)^\s*using\s+[^;]+;\s*$")
        using_lines = [match.group(0).strip() for match in using_pattern.finditer(source)]
        body = using_pattern.sub("", source).strip()
        indented = textwrap.indent(body, "    ")
        prefix = "\n".join(dict.fromkeys(using_lines))
        if prefix:
            prefix = f"{prefix}\n\n"
        return (
            f"{prefix}"
            "public sealed partial class UserCode\n"
            "{\n"
            f"{indented}\n"
            "}\n"
        )

    def _entrypoint_check_source(self, entrypoint: str) -> str:
        return textwrap.dedent(
            f"""
            using System.Collections.Generic;

            public sealed partial class UserCode
            {{
                public object? __ValidateEntrypointSignature(Dictionary<string, object?> args, Dictionary<string, object?> state)
                {{
                    return {entrypoint}(args, state);
                }}
            }}
            """
        ).strip()

    def _csharp_member_name(self, raw: str) -> str:
        parts: list[str] = []
        current: list[str] = []
        for ch in raw:
            if ch.isalnum():
                current.append(ch)
            elif current:
                parts.append("".join(current))
                current = []
        if current:
            parts.append("".join(current))
        if not parts:
            return "CallCapability"
        name = "".join(part[:1].upper() + part[1:] for part in parts)
        if name[:1].isdigit():
            name = f"Call{name}"
        return name

    def _csharp_identifier(self, raw: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw).strip("_")
        if not cleaned:
            cleaned = "capabilities"
        if cleaned[0].isdigit():
            cleaned = f"capabilities_{cleaned}"
        if cleaned in {"class", "namespace", "event", "delegate", "operator", "params"}:
            cleaned = f"{cleaned}_"
        return cleaned[:1].lower() + cleaned[1:]

    def _sdk_source(self, request: CodeExecutionRequest | CodeValidationRequest) -> str:
        grouped: dict[str, dict[str, str]] = {}
        for capability in request.capability_manifest.capabilities:
            if "." not in capability.name:
                continue
            default_namespace, default_method = capability.name.split(".", 1)
            namespace = capability.sdk_namespace or default_namespace
            method = capability.sdk_method or default_method
            grouped.setdefault(namespace, {})[method] = capability.name

        chunks = [
            "using System.Collections.Generic;",
            "using System.Threading.Tasks;",
            "",
            "public abstract class CapabilityNamespaceBase",
            "{",
            "    protected Task<object?> CallCapability(string name, Dictionary<string, object?> kwargs) => UserCode.Capability(name, kwargs);",
            "}",
            "",
        ]
        properties: list[str] = []
        for namespace in sorted(grouped):
            property_name = self._csharp_identifier(namespace)
            type_name = f"{self._csharp_member_name(namespace)}Namespace"
            properties.append(f"    public static {type_name} {property_name} {{ get; }} = new();")
            chunks.append(f"public sealed class {type_name} : CapabilityNamespaceBase")
            chunks.append("{")
            if namespace == "tools":
                chunks.append(
                    '    public Task<object?> Call(string method, Dictionary<string, object?> kwargs) => CallCapability("tools." + method, kwargs);'
                )
            else:
                chunks.append(
                    "    public Task<object?> Call(string method, Dictionary<string, object?> kwargs)"
                )
                chunks.append("    {")
                chunks.append("        return method switch")
                chunks.append("        {")
                for method, capability_name in sorted(grouped[namespace].items()):
                    chunks.append(
                        f"            {json.dumps(method)} => CallCapability({json.dumps(capability_name)}, kwargs),"
                    )
                chunks.append(
                    f'            _ => throw new System.InvalidOperationException($"capability method is not declared in manifest: {namespace}.{{method}}"),'
                )
                chunks.append("        };")
                chunks.append("    }")
            used_methods = {"Call"}
            for method, capability_name in sorted(grouped[namespace].items()):
                csharp_method = self._csharp_member_name(method)
                if csharp_method in used_methods:
                    csharp_method = f"{csharp_method}Capability"
                used_methods.add(csharp_method)
                chunks.append(
                    f"    public Task<object?> {csharp_method}(Dictionary<string, object?> kwargs) => CallCapability({json.dumps(capability_name)}, kwargs);"
                )
            chunks.append("}")
            chunks.append("")
        chunks.append("public sealed partial class UserCode")
        chunks.append("{")
        chunks.extend(properties)
        chunks.append("}")
        chunks.append("")
        return "\n".join(chunks)

    def _runner_source(self) -> str:
        return textwrap.dedent(
            f"""
            using System;
            using System.Collections.Generic;
            using System.Linq;
            using System.Net.Http;
            using System.Reflection;
            using System.Runtime.ExceptionServices;
            using System.Text;
            using System.Text.Json;
            using System.Text.Json.Serialization;
            using System.Threading.Tasks;

            public sealed class ExecutionRequest
            {{
                [JsonPropertyName("kind")]
                public string Kind {{ get; set; }} = "";

                [JsonPropertyName("language")]
                public string Language {{ get; set; }} = "csharp";

                [JsonPropertyName("code")]
                public string Code {{ get; set; }} = "";

                [JsonPropertyName("entrypoint")]
                public string? Entrypoint {{ get; set; }}

                [JsonPropertyName("wall_time_limit_seconds")]
                public int WallTimeLimitSeconds {{ get; set; }}

                [JsonPropertyName("args")]
                public Dictionary<string, object?> Args {{ get; set; }} = new();

                [JsonPropertyName("state")]
                public Dictionary<string, object?> State {{ get; set; }} = new();

                [JsonPropertyName("context")]
                public Dictionary<string, object?> Context {{ get; set; }} = new();

                [JsonPropertyName("capability_manifest")]
                public Dictionary<string, object?> CapabilityManifest {{ get; set; }} = new();
            }}

            public sealed class CapabilityInterruptError : Exception
            {{
                public CapabilityInterruptError(Dictionary<string, object?> payload) : base("Capability interrupt")
                {{
                    Payload = payload;
                }}

                public Dictionary<string, object?> Payload {{ get; }}
            }}

            public sealed partial class UserCode
            {{
                private static readonly HttpClient Http = new();
                public static ExecutionRequest CurrentRequest {{ get; set; }} = new();
                public static string GatewayUrl {{ get; set; }} = "";

                public static async Task<object?> Capability(string name, Dictionary<string, object?> kwargs)
                {{
                    if (!Program.ManifestCapabilityNames(CurrentRequest).Contains(name))
                    {{
                        throw new InvalidOperationException($"Capability is not declared in manifest: {{name}}");
                    }}
                    var payload = new Dictionary<string, object?>
                    {{
                        ["context"] = CurrentRequest.Context,
                        ["name"] = name,
                        ["args"] = new List<object?>(),
                        ["kwargs"] = kwargs,
                        ["state"] = CurrentRequest.State,
                    }};
                    using var content = new StringContent(
                        JsonSerializer.Serialize(payload, Program.JsonOptions),
                        Encoding.UTF8,
                        "application/json"
                    );
                    using var httpRequest = new HttpRequestMessage(HttpMethod.Post, GatewayUrl + "{CAPABILITY_CALL_PATH}")
                    {{
                        Content = content,
                    }};
                    if (CurrentRequest.Context.TryGetValue("request_id", out var requestId) && requestId is string requestIdValue && requestIdValue.Length > 0)
                    {{
                        httpRequest.Headers.TryAddWithoutValidation("X-Request-Id", requestIdValue);
                    }}
                    if (CurrentRequest.Context.TryGetValue("trace_id", out var traceId) && traceId is string traceIdValue && traceIdValue.Length > 0)
                    {{
                        httpRequest.Headers.TryAddWithoutValidation("X-Trace-Id", traceIdValue);
                    }}
                    using var response = await Http.SendAsync(httpRequest);
                    var responseBody = await response.Content.ReadAsStringAsync();
                    if (!response.IsSuccessStatusCode)
                    {{
                        throw new InvalidOperationException($"Capability {{name}} failed: {{(int)response.StatusCode}} {{responseBody}}");
                    }}
                    var decoded = Program.NormalizeDictionary(
                        JsonSerializer.Deserialize<Dictionary<string, object?>>(responseBody, Program.JsonOptions)
                    );
                    if (decoded.TryGetValue("state", out var returnedState) && returnedState is Dictionary<string, object?> returnedStateDict)
                    {{
                        CurrentRequest.State.Clear();
                        foreach (var pair in returnedStateDict)
                        {{
                            CurrentRequest.State[pair.Key] = pair.Value;
                        }}
                    }}
                    if (decoded.TryGetValue("status", out var status) && status is string statusValue && statusValue == "interrupt")
                    {{
                        throw new CapabilityInterruptError(decoded);
                    }}
                    return decoded.TryGetValue("result", out var result) ? result : null;
                }}
            }}

            public static class Program
            {{
                public const string ResponsePrefix = "{RESPONSE_PREFIX}";

                public static readonly JsonSerializerOptions JsonOptions = new()
                {{
                    PropertyNameCaseInsensitive = true,
                    WriteIndented = false,
                }};

                public static HashSet<string> ManifestCapabilityNames(ExecutionRequest request)
                {{
                    var names = new HashSet<string>();
                    if (!request.CapabilityManifest.TryGetValue("capabilities", out var rawCapabilities))
                    {{
                        return names;
                    }}
                    if (rawCapabilities is not List<object?> capabilities)
                    {{
                        return names;
                    }}
                    foreach (var rawCapability in capabilities)
                    {{
                        if (rawCapability is not Dictionary<string, object?> capability)
                        {{
                            continue;
                        }}
                        if (capability.TryGetValue("name", out var rawName) && rawName is string name && name.Length > 0)
                        {{
                            names.Add(name);
                        }}
                    }}
                    return names;
                }}

                public static async Task Main(string[] args)
                {{
                    var stage = "bootstrap";
                    var request = new ExecutionRequest();
                    try
                    {{
                        if (args.Length != 2)
                        {{
                            throw new InvalidOperationException("usage: runner <request.json> <gateway-url>");
                        }}
                        var requestText = await System.IO.File.ReadAllTextAsync(args[0]);
                        request = JsonSerializer.Deserialize<ExecutionRequest>(requestText, JsonOptions) ?? new ExecutionRequest();
                        request.Args = NormalizeDictionary(request.Args);
                        request.State = NormalizeDictionary(request.State);
                        request.Context = NormalizeDictionary(request.Context);
                        request.CapabilityManifest = NormalizeDictionary(request.CapabilityManifest);
                        UserCode.CurrentRequest = request;
                        UserCode.GatewayUrl = args[1];

                        stage = "user";
                        var result = await InvokeEntrypoint(request);
                        var stateReturned = object.ReferenceEquals(result, request.State);
                        Emit(new Dictionary<string, object?>
                        {{
                            ["status"] = "completed",
                            ["result"] = stateReturned ? null : result,
                            ["state"] = request.State,
                            ["state_returned"] = stateReturned,
                            ["logs"] = new List<object?>(),
                        }});
                    }}
                    catch (CapabilityInterruptError interrupt)
                    {{
                        Emit(new Dictionary<string, object?>
                        {{
                            ["status"] = "interrupted",
                            ["result"] = interrupt.Payload.TryGetValue("result", out var result) ? result : null,
                            ["state"] = request.State,
                            ["interrupt"] = interrupt.Payload.TryGetValue("interrupt", out var interruptPayload) ? interruptPayload : null,
                            ["logs"] = new List<object?>(),
                        }});
                    }}
                    catch (Exception exc)
                    {{
                        Emit(new Dictionary<string, object?>
                        {{
                            ["status"] = "failed",
                            ["result"] = null,
                            ["state"] = request.State,
                            ["error"] = new Dictionary<string, object?>
                            {{
                                ["language"] = request.Language,
                                ["service"] = "{SERVICE_NAME}",
                                ["stage"] = stage,
                                ["message"] = exc.Message,
                                ["exception_type"] = exc.GetType().Name,
                                ["traceback"] = exc.ToString(),
                                ["request_id"] = ContextString(request, "request_id"),
                                ["trace_id"] = ContextString(request, "trace_id"),
                            }},
                            ["logs"] = new List<object?>(),
                        }});
                    }}
                }}

                private static async Task<object?> InvokeEntrypoint(ExecutionRequest request)
                {{
                    var bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly;
                    var methods = typeof(UserCode)
                        .GetMethods(bindingFlags)
                        .Where(method => !method.IsSpecialName && method.Name != nameof(UserCode.Capability))
                        .OrderBy(method => method.MetadataToken)
                        .ToList();
                    var method = string.IsNullOrWhiteSpace(request.Entrypoint)
                        ? methods.FirstOrDefault()
                        : methods.FirstOrDefault(candidate => candidate.Name == request.Entrypoint);
                    if (method is null)
                    {{
                        throw new MissingMethodException("Entrypoint function not found: declare at least one function");
                    }}
                    var parameters = method.GetParameters();
                    if (parameters.Length != 2)
                    {{
                        throw new InvalidOperationException("Entrypoint must accept exactly (Dictionary<string, object?> args, Dictionary<string, object?> state)");
                    }}

                    object? target = method.IsStatic ? null : new UserCode();
                    object? rawResult;
                    try
                    {{
                        rawResult = method.Invoke(target, new object?[] {{ request.Args, request.State }});
                    }}
                    catch (TargetInvocationException exc) when (exc.InnerException is not null)
                    {{
                        ExceptionDispatchInfo.Capture(exc.InnerException).Throw();
                        throw;
                    }}

                    if (rawResult is Task task)
                    {{
                        await task;
                        var resultProperty = task.GetType().GetProperty("Result");
                        return resultProperty?.GetValue(task);
                    }}
                    return rawResult;
                }}

                public static Dictionary<string, object?> NormalizeDictionary(Dictionary<string, object?>? raw)
                {{
                    var normalized = new Dictionary<string, object?>();
                    if (raw is null)
                    {{
                        return normalized;
                    }}
                    foreach (var pair in raw)
                    {{
                        normalized[pair.Key] = NormalizeValue(pair.Value);
                    }}
                    return normalized;
                }}

                private static object? NormalizeValue(object? value)
                {{
                    if (value is JsonElement element)
                    {{
                        return NormalizeJsonElement(element);
                    }}
                    if (value is Dictionary<string, object?> dict)
                    {{
                        return NormalizeDictionary(dict);
                    }}
                    if (value is List<object?> list)
                    {{
                        return list.Select(NormalizeValue).ToList();
                    }}
                    return value;
                }}

                private static object? NormalizeJsonElement(JsonElement element)
                {{
                    return element.ValueKind switch
                    {{
                        JsonValueKind.Object => element.EnumerateObject().ToDictionary(prop => prop.Name, prop => NormalizeJsonElement(prop.Value)),
                        JsonValueKind.Array => element.EnumerateArray().Select(NormalizeJsonElement).ToList(),
                        JsonValueKind.String => element.GetString(),
                        JsonValueKind.Number => element.TryGetInt64(out var longValue) ? longValue : element.GetDouble(),
                        JsonValueKind.True => true,
                        JsonValueKind.False => false,
                        _ => null,
                    }};
                }}

                private static object? ContextString(ExecutionRequest request, string key)
                {{
                    return request.Context.TryGetValue(key, out var value) ? value : null;
                }}

                private static void Emit(Dictionary<string, object?> payload)
                {{
                    Console.WriteLine(ResponsePrefix + JsonSerializer.Serialize(payload, JsonOptions));
                }}
            }}
            """
        ).strip()
