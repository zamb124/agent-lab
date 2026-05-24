"""Go sandbox executor по контракту CodeExecutionRequest."""

from __future__ import annotations

import asyncio
import hashlib
import json
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
)
from core.capabilities.runtime_executables import (
    resolve_runtime_executable,
    runtime_executable_required_message,
)
from core.config import get_settings
from core.tracing.operation_span import traced_operation

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"
RESPONSE_PREFIX = "__CODE_RUNNER_RESPONSE__"
SERVICE_NAME = "code_runner_go"
GO_BIN_ENV = "CODE_RUNNER_GO_BIN"


class GoSandboxExecutor:
    """Исполняет Go user code через cached build artifact."""

    def __init__(self) -> None:
        self._artifact_root: Path = Path(tempfile.mkdtemp(prefix="code-runner-go-artifacts-"))
        self._build_locks: dict[str, asyncio.Lock] = {}
        self._build_locks_guard: asyncio.Lock = asyncio.Lock()

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        if request.language != "go":
            return self._failed_response(
                request=request,
                stage="validation",
                message=f"code-runner-go cannot execute language={request.language}",
                exception_type="UnsupportedLanguageError",
            )

        entrypoint = request.entrypoint.strip() if isinstance(request.entrypoint, str) and request.entrypoint.strip() else self._infer_entrypoint(request.code)
        if entrypoint is None:
            return self._failed_response(
                request=request,
                stage="validation",
                message="Entrypoint function not found: declare at least one function",
                exception_type="EntrypointNotFoundError",
            )
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint) is None:
            return self._failed_response(
                request=request,
                stage="validation",
                message=f"invalid Go entrypoint name: {entrypoint!r}",
                exception_type="InvalidEntrypointError",
            )

        go_bin = resolve_runtime_executable("go", override_env=GO_BIN_ENV)
        if go_bin is None:
            return self._failed_response(
                request=request,
                stage="runtime",
                message=runtime_executable_required_message("go", override_env=GO_BIN_ENV),
                exception_type="MissingRuntimeExecutableError",
            )

        gateway_url = get_settings().server.get_service_url("capability_gateway")
        async with traced_operation(
            "code_runner_go.execute",
            event_type="code_runner.execute",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": entrypoint,
                "platform.code_runner.runtime": "build_artifact_cache",
            },
        ):
            artifact_key = self._artifact_key(request, entrypoint)
            artifact_path = self._artifact_root / artifact_key
            binary_path = artifact_path / "sandbox"
            try:
                await self._ensure_artifact(
                    request=request,
                    go_bin=go_bin,
                    entrypoint=entrypoint,
                    artifact_path=artifact_path,
                    binary_path=binary_path,
                )
            except Exception as exc:
                return self._failed_response(
                    request=request,
                    stage="compile",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            with tempfile.TemporaryDirectory(prefix="code-runner-go-call-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                request_path = tmp_path / "request.json"
                _ = request_path.write_text(request.model_dump_json(), encoding="utf-8")
                completed = await self._run_go(
                    request=request,
                    binary_path=binary_path,
                    request_path=request_path,
                    gateway_url=gateway_url,
                    wall_time_limit_seconds=request.wall_time_limit_seconds,
                )
        return completed

    async def validate(self, request: CodeValidationRequest) -> CodeValidationResponse:
        if request.language != "go":
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message=f"code-runner-go cannot validate language={request.language}",
                exception_type="UnsupportedLanguageError",
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
                message=f"invalid Go entrypoint name: {entrypoint!r}",
                exception_type="InvalidEntrypointError",
            )

        go_bin = resolve_runtime_executable("go", override_env=GO_BIN_ENV)
        if go_bin is None:
            return self._failed_validation_response(
                request=request,
                stage="runtime",
                message=runtime_executable_required_message("go", override_env=GO_BIN_ENV),
                exception_type="MissingRuntimeExecutableError",
            )

        async with traced_operation(
            "code_runner_go.validate",
            event_type="code_runner.validate",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": entrypoint,
                "platform.code_runner.runtime": "build_artifact_cache",
            },
        ):
            artifact_key = self._artifact_key(request, entrypoint)
            artifact_path = self._artifact_root / artifact_key
            binary_path = artifact_path / "sandbox"
            try:
                await self._ensure_artifact(
                    request=request,
                    go_bin=go_bin,
                    entrypoint=entrypoint,
                    artifact_path=artifact_path,
                    binary_path=binary_path,
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

    def _artifact_key(self, request: CodeExecutionRequest | CodeValidationRequest, entrypoint: str) -> str:
        payload = {
            "language": request.language,
            "code": request.code,
            "entrypoint": entrypoint,
            "capability_manifest": request.capability_manifest.model_dump(mode="json"),
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
        go_bin: str,
        entrypoint: str,
        artifact_path: Path,
        binary_path: Path,
    ) -> None:
        if binary_path.exists():
            return
        lock = await self._build_lock(artifact_path.name)
        async with lock:
            if binary_path.exists():
                return
            artifact_path.mkdir(parents=True, exist_ok=True)
            runner_path = artifact_path / "runner.go"
            user_path = artifact_path / "user.go"
            entrypoint_path = artifact_path / "entrypoint.go"
            sdk_path = artifact_path / "sdk.go"
            _ = runner_path.write_text(self._runner_source(), encoding="utf-8")
            _ = user_path.write_text(request.code, encoding="utf-8")
            _ = entrypoint_path.write_text(self._entrypoint_source(entrypoint), encoding="utf-8")
            _ = sdk_path.write_text(self._sdk_source(request), encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                go_bin,
                "build",
                "-o",
                str(binary_path),
                str(runner_path),
                str(user_path),
                str(entrypoint_path),
                str(sdk_path),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(artifact_path),
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    "go artifact build failed: "
                    + stdout.decode("utf-8", errors="replace")
                    + stderr.decode("utf-8", errors="replace")
                )

    async def _run_go(
        self,
        *,
        request: CodeExecutionRequest,
        binary_path: Path,
        request_path: Path,
        gateway_url: str,
        wall_time_limit_seconds: int,
    ) -> CodeExecutionResponse:
        process = await asyncio.create_subprocess_exec(
            str(binary_path),
            str(request_path),
            gateway_url,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                message="go sandbox exceeded wall time limit",
                exception_type=type(exc).__name__,
                traceback_text="".join(traceback.format_exception(exc)),
            )
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            return self._failed_response(
                request=request,
                stage="process",
                message=f"go sandbox process exited with code {process.returncode}",
                exception_type="GoSandboxProcessError",
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

    def _extract_response_line(self, stdout_text: str) -> str:
        for line in reversed(stdout_text.splitlines()):
            if line.startswith(RESPONSE_PREFIX):
                return line.removeprefix(RESPONSE_PREFIX)
        raise RuntimeError("go sandbox did not return execution response")

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

    def _infer_entrypoint(self, code: str) -> str | None:
        match = re.search(r"func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
        return match.group(1) if match else None

    def _entrypoint_source(self, entrypoint: str) -> str:
        return textwrap.dedent(
            f"""
            package main

            func callEntrypoint(args map[string]any, state map[string]any) (any, error) {{
                return {entrypoint}(args, state)
            }}
            """
        ).strip()

    def _go_exported_name(self, raw: str) -> str:
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
            return "Call"
        name = "".join(part[:1].upper() + part[1:] for part in parts)
        if name[:1].isdigit():
            name = f"Call{name}"
        return name

    def _go_namespace_name(self, raw: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw).strip("_")
        if not cleaned:
            cleaned = "capabilities"
        if cleaned[0].isdigit():
            cleaned = f"capabilities_{cleaned}"
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

        chunks = ["package main", ""]
        for namespace in sorted(grouped):
            var_name = self._go_namespace_name(namespace)
            type_name = f"{var_name}Namespace"
            chunks.append(f"type {type_name} struct{{}}")
            chunks.append(f"var {var_name} {type_name}")
            chunks.append("")
            chunks.append(
                f"func ({type_name}) Call(method string, kwargs map[string]any) (any, error) {{"
            )
            chunks.append(f'    return Capability("{namespace}." + method, kwargs)')
            chunks.append("}")
            chunks.append("")
            for method, capability_name in sorted(grouped[namespace].items()):
                go_method = self._go_exported_name(method)
                chunks.append(
                    f"func ({type_name}) {go_method}(kwargs map[string]any) (any, error) {{"
                )
                chunks.append(f'    return Capability("{capability_name}", kwargs)')
                chunks.append("}")
                chunks.append("")
        return "\n".join(chunks).strip() + "\n"

    def _runner_source(self) -> str:
        return textwrap.dedent(
            f"""
            package main

            import (
                "bytes"
                "encoding/json"
                "fmt"
                "io"
                nethttp "net/http"
                "os"
                "reflect"
                "runtime/debug"
            )

            const capabilityCallPath = "{CAPABILITY_CALL_PATH}"
            const responsePrefix = "{RESPONSE_PREFIX}"

            type ExecutionRequest struct {{
                Kind string `json:"kind"`
                Language string `json:"language"`
                Code string `json:"code"`
                Entrypoint string `json:"entrypoint"`
                WallTimeLimitSeconds int `json:"wall_time_limit_seconds"`
                Args map[string]any `json:"args"`
                State map[string]any `json:"state"`
                Context map[string]any `json:"context"`
                CapabilityManifest map[string]any `json:"capability_manifest"`
            }}

            var currentRequest ExecutionRequest
            var gatewayURL string

            type CapabilityInterruptError struct {{
                Payload map[string]any
            }}

            func (e CapabilityInterruptError) Error() string {{
                return "capability interrupt"
            }}

            func contextString(key string) any {{
                if currentRequest.Context == nil {{
                    return nil
                }}
                value, ok := currentRequest.Context[key]
                if !ok {{
                    return nil
                }}
                return value
            }}

            func emitFailure(stage string, err any) {{
                message := fmt.Sprint(err)
                traceback := fmt.Sprintf("%s\\n%s", message, string(debug.Stack()))
                responsePayload := map[string]any{{
                    "status": "failed",
                    "result": nil,
                    "state": currentRequest.State,
                    "error": map[string]any{{
                        "language": currentRequest.Language,
                        "service": "{SERVICE_NAME}",
                        "stage": stage,
                        "message": message,
                        "exception_type": "GoError",
                        "traceback": traceback,
                        "request_id": contextString("request_id"),
                        "trace_id": contextString("trace_id"),
                    }},
                    "logs": []any{{}},
                }}
                responseBytes, marshalErr := json.Marshal(responsePayload)
                if marshalErr != nil {{
                    fmt.Println(responsePrefix + `{{"status":"failed","state":{{}},"error":{{"language":"go","service":"{SERVICE_NAME}","stage":"failure_encode","message":"failed to encode error","exception_type":"GoError"}},"logs":[]}}`)
                    return
                }}
                fmt.Println(responsePrefix + string(responseBytes))
            }}

            func emitInterrupt(payload map[string]any) {{
                responsePayload := map[string]any{{
                    "status": "interrupted",
                    "result": payload["result"],
                    "state": currentRequest.State,
                    "interrupt": payload["interrupt"],
                    "logs": []any{{}},
                }}
                responseBytes, marshalErr := json.Marshal(responsePayload)
                if marshalErr != nil {{
                    emitFailure("interrupt_encode", marshalErr)
                    return
                }}
                fmt.Println(responsePrefix + string(responseBytes))
            }}

            func Capability(name string, kwargs map[string]any) (any, error) {{
                payload := map[string]any{{
                    "context": currentRequest.Context,
                    "name": name,
                    "args": []any{{}},
                    "kwargs": kwargs,
                    "state": currentRequest.State,
                }}
                body, err := json.Marshal(payload)
                if err != nil {{
                    return nil, err
                }}
                httpRequest, err := nethttp.NewRequest("POST", gatewayURL + capabilityCallPath, bytes.NewReader(body))
                if err != nil {{
                    return nil, err
                }}
                httpRequest.Header.Set("Content-Type", "application/json")
                if requestID, ok := currentRequest.Context["request_id"].(string); ok && requestID != "" {{
                    httpRequest.Header.Set("X-Request-Id", requestID)
                }}
                if traceID, ok := currentRequest.Context["trace_id"].(string); ok && traceID != "" {{
                    httpRequest.Header.Set("X-Trace-Id", traceID)
                }}
                response, err := nethttp.DefaultClient.Do(httpRequest)
                if err != nil {{
                    return nil, err
                }}
                defer response.Body.Close()
                responseBody, err := io.ReadAll(response.Body)
                if err != nil {{
                    return nil, err
                }}
                if response.StatusCode < 200 || response.StatusCode >= 300 {{
                    return nil, fmt.Errorf("capability %s failed: %d %s", name, response.StatusCode, string(responseBody))
                }}
                var decoded map[string]any
                if err := json.Unmarshal(responseBody, &decoded); err != nil {{
                    return nil, err
                }}
                if returnedState, ok := decoded["state"].(map[string]any); ok {{
                    for key := range currentRequest.State {{
                        delete(currentRequest.State, key)
                    }}
                    for key, value := range returnedState {{
                        currentRequest.State[key] = value
                    }}
                }}
                statusValue, ok := decoded["status"].(string)
                if !ok {{
                    return nil, fmt.Errorf("capability %s returned invalid status", name)
                }}
                if statusValue == "interrupt" {{
                    return nil, CapabilityInterruptError{{Payload: decoded}}
                }}
                return decoded["result"], nil
            }}

            func main() {{
                stage := "bootstrap"
                defer func() {{
                    if recovered := recover(); recovered != nil {{
                        emitFailure(stage, recovered)
                    }}
                }}()
                if len(os.Args) != 3 {{
                    panic("usage: runner <request.json> <gateway-url>")
                }}
                requestBytes, err := os.ReadFile(os.Args[1])
                if err != nil {{
                    panic(err)
                }}
                gatewayURL = os.Args[2]
                if err := json.Unmarshal(requestBytes, &currentRequest); err != nil {{
                    panic(err)
                }}
                stage = "user"
                result, err := callEntrypoint(currentRequest.Args, currentRequest.State)
                if err != nil {{
                    if interruptErr, ok := err.(CapabilityInterruptError); ok {{
                        emitInterrupt(interruptErr.Payload)
                        return
                    }}
                    emitFailure(stage, err)
                    return
                }}
                stateReturned := false
                if resultMap, ok := result.(map[string]any); ok {{
                    stateReturned = reflect.ValueOf(resultMap).Pointer() == reflect.ValueOf(currentRequest.State).Pointer()
                }}
                responsePayload := map[string]any{{
                    "status": "completed",
                    "result": nil,
                    "state": currentRequest.State,
                    "state_returned": stateReturned,
                    "logs": []any{{}},
                }}
                if !stateReturned {{
                    responsePayload["result"] = result
                }}
                responseBytes, err := json.Marshal(responsePayload)
                if err != nil {{
                    panic(err)
                }}
                fmt.Println(responsePrefix + string(responseBytes))
            }}
            """
        ).strip()
