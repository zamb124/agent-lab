"""Python sandbox executor по контракту CodeExecutionRequest.

Целевой runtime: code-runner-python держит long-lived worker pool.
Worker компилирует source один раз по artifact-key и дальше исполняет cached
code object в свежем sandbox namespace на каждый вызов.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
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
from core.config import get_settings
from core.tracing.operation_span import traced_operation

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"
SERVICE_NAME = "code_runner_python"
WORKER_POOL_ENV = "CODE_RUNNER_PYTHON_WORKERS"


class _PythonWorker:
    """Один persistent Python sandbox worker с JSON-lines IPC."""

    def __init__(self, *, worker_path: Path, gateway_url: str):
        self._worker_path = worker_path
        self._gateway_url = gateway_url
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None

    async def invoke(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        async with self._lock:
            process = await self._ensure_process()
            assert process.stdin is not None
            assert process.stdout is not None
            payload = request.model_dump_json().encode("utf-8") + b"\n"
            try:
                process.stdin.write(payload)
                await process.stdin.drain()
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=float(request.wall_time_limit_seconds),
                )
            except TimeoutError as exc:
                await self._restart()
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="timeout",
                    message="python sandbox exceeded wall time limit",
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            except Exception as exc:
                await self._restart()
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            if not line:
                await self._restart()
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message="python sandbox worker exited without response",
                    exception_type="PythonSandboxWorkerExited",
                )
            try:
                return CodeExecutionResponse.model_validate_json(line.decode("utf-8"))
            except Exception as exc:
                await self._restart()
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="response_parse",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                    stdout=line.decode("utf-8", errors="replace"),
                )

    async def validate(self, request: CodeValidationRequest) -> CodeValidationResponse:
        async with self._lock:
            process = await self._ensure_process()
            assert process.stdin is not None
            assert process.stdout is not None
            payload = request.model_dump_json().encode("utf-8") + b"\n"
            try:
                process.stdin.write(payload)
                await process.stdin.drain()
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=float(request.wall_time_limit_seconds),
                )
            except TimeoutError as exc:
                await self._restart()
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="timeout",
                    message="python sandbox validation exceeded wall time limit",
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            except Exception as exc:
                await self._restart()
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            if not line:
                await self._restart()
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message="python sandbox worker exited without validation response",
                    exception_type="PythonSandboxWorkerExited",
                )
            try:
                return CodeValidationResponse.model_validate_json(line.decode("utf-8"))
            except Exception as exc:
                await self._restart()
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="response_parse",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                    stdout=line.decode("utf-8", errors="replace"),
                )

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-S",
            str(self._worker_path),
            self._gateway_url,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return self._process

    async def _restart(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        process.kill()
        _ = await process.wait()


class PythonSandboxExecutor:
    """Исполняет Python user code через persistent sandbox worker pool."""

    def __init__(self) -> None:
        self._workers: list[_PythonWorker] = []
        self._next_worker = 0
        self._pool_lock = asyncio.Lock()
        self._runtime_dir = Path(tempfile.mkdtemp(prefix="code-runner-python-runtime-"))
        self._worker_path = self._runtime_dir / "python_worker.py"
        self._worker_path.write_text(self._worker_source(), encoding="utf-8")

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        if request.language != "python":
            return self._failed_response(
                request=request,
                stage="validation",
                message=f"code-runner-python cannot execute language={request.language}",
                exception_type="UnsupportedLanguageError",
            )

        async with traced_operation(
            "code_runner_python.execute",
            event_type="code_runner.execute",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": request.entrypoint or "<first_function>",
                "platform.code_runner.runtime": "warm_worker_pool",
            },
        ):
            try:
                worker = await self._select_worker()
                return await worker.invoke(request)
            except Exception as exc:
                return self._failed_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )

    async def validate(self, request: CodeValidationRequest) -> CodeValidationResponse:
        if request.language != "python":
            return self._failed_validation_response(
                request=request,
                stage="validation",
                message=f"code-runner-python cannot validate language={request.language}",
                exception_type="UnsupportedLanguageError",
            )

        async with traced_operation(
            "code_runner_python.validate",
            event_type="code_runner.validate",
            operation_category="code_runner",
            extra_attributes={
                "platform.code_runner.language": request.language,
                "platform.code_runner.kind": request.kind,
                "platform.code_runner.entrypoint": request.entrypoint or "<first_function>",
                "platform.code_runner.runtime": "warm_worker_pool",
            },
        ):
            try:
                worker = await self._select_worker()
                return await worker.validate(request)
            except Exception as exc:
                return self._failed_validation_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )

    async def _select_worker(self) -> _PythonWorker:
        async with self._pool_lock:
            if not self._workers:
                gateway_url = get_settings().server.get_service_url("capability_gateway")
                count = self._worker_count()
                self._workers = [
                    _PythonWorker(worker_path=self._worker_path, gateway_url=gateway_url)
                    for _ in range(count)
                ]
            worker = self._workers[self._next_worker % len(self._workers)]
            self._next_worker += 1
            return worker

    def _worker_count(self) -> int:
        raw = os.environ.get(WORKER_POOL_ENV)
        if raw is None:
            return max(2, min(8, (os.cpu_count() or 2)))
        return max(1, int(raw))

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

    def _worker_source(self) -> str:
        return textwrap.dedent(
            f"""
            import asyncio
            import ast
            import builtins
            import __future__
            import hashlib
            import inspect
            import io
            import json
            import math
            import sys
            import traceback
            import typing
            import urllib.error
            import urllib.request

            gateway_url = sys.argv[1]
            capability_call_path = {json.dumps(CAPABILITY_CALL_PATH)}
            compiled_cache = {{}}


            class CapabilityInterrupt(Exception):
                def __init__(self, payload):
                    self.payload = payload
                    super().__init__("Capability interrupt")


            class FlowInterrupt(Exception):
                def __init__(self, question=None, *, body=None, **kwargs):
                    if body is not None:
                        if question is not None:
                            raise ValueError("FlowInterrupt: pass question or body, not both")
                        if not isinstance(body, dict):
                            raise TypeError("FlowInterrupt.body must be a dict")
                        self.body = dict(body)
                    elif question is not None:
                        if not isinstance(question, str) or not question.strip():
                            raise ValueError("FlowInterrupt.question must be a non-empty string")
                        self.body = {{"kind": "user_message", "question": question.strip()}}
                    else:
                        raise ValueError("FlowInterrupt: question or body is required")
                    self.extra = dict(kwargs)
                    super().__init__(self.body.get("question", "Flow interrupted"))


            class AttrDict(dict):
                def __getattr__(self, name):
                    try:
                        return self[name]
                    except KeyError as exc:
                        raise AttributeError(name) from exc

                def __setattr__(self, name, value):
                    self[name] = value

                def __delattr__(self, name):
                    try:
                        del self[name]
                    except KeyError as exc:
                        raise AttributeError(name) from exc


            def _wrap_attr(value):
                if isinstance(value, AttrDict):
                    return value
                if isinstance(value, dict):
                    return AttrDict({{key: _wrap_attr(item) for key, item in value.items()}})
                if isinstance(value, list):
                    return [_wrap_attr(item) for item in value]
                return value


            async def capability(capability_name, **kwargs):
                payload = json.dumps({{
                    "context": current_request["context"],
                    "name": capability_name,
                    "args": [],
                    "kwargs": kwargs,
                    "state": current_request["state"],
                }}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                context = current_request["context"]
                headers = {{"Content-Type": "application/json"}}
                if context.get("request_id"):
                    headers["X-Request-Id"] = context["request_id"]
                if context.get("trace_id"):
                    headers["X-Trace-Id"] = context["trace_id"]
                http_request = urllib.request.Request(
                    gateway_url + capability_call_path,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(http_request, timeout=120.0) as response:
                        response_body = response.read()
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Capability {{capability_name}} failed: {{exc.code}} {{error_body}}"
                    ) from exc
                decoded = json.loads(response_body.decode("utf-8"))
                returned_state = decoded.get("state")
                if isinstance(returned_state, dict):
                    current_request["state"].clear()
                    current_request["state"].update(_wrap_attr(returned_state))
                if decoded.get("status") == "interrupt":
                    raise CapabilityInterrupt(decoded)
                return decoded.get("result")


            class CapabilityNamespace:
                def __init__(self, namespace, mapping):
                    self._namespace = namespace
                    self._mapping = dict(mapping)

                def __getattr__(self, method):
                    capability_name = self._mapping.get(method)
                    if capability_name is None:
                        raise AttributeError(f"Unknown capability method: {{self._namespace}}.{{method}}")

                    async def call(**kwargs):
                        return await capability(capability_name, **kwargs)

                    return call

                async def call(self, method, **kwargs):
                    capability_name = self._mapping.get(method, f"{{self._namespace}}.{{method}}")
                    return await capability(capability_name, **kwargs)


            def build_sdk_namespaces():
                manifest = current_request.get("capability_manifest") or {{}}
                capabilities = manifest.get("capabilities") or []
                namespace_maps = {{}}
                for item in capabilities:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) or "." not in name:
                        continue
                    namespace = item.get("sdk_namespace")
                    method = item.get("sdk_method")
                    if not isinstance(namespace, str) or not namespace:
                        namespace = name.split(".", 1)[0]
                    if not isinstance(method, str) or not method:
                        method = name.split(".", 1)[1]
                    namespace_maps.setdefault(namespace, {{}})[method] = name
                return {{
                    namespace: CapabilityNamespace(namespace, mapping)
                    for namespace, mapping in namespace_maps.items()
                }}


            def build_namespace():
                allowed_import_roots = {{
                    "__future__", "asyncio", "ast", "base64", "collections", "datetime", "decimal",
                    "functools", "hashlib", "html", "itertools", "json", "math", "operator",
                    "random", "re", "statistics", "string", "time", "typing", "uuid",
                }}

                def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
                    if level != 0:
                        raise ImportError("relative imports are not allowed in code runner")
                    root = name.split(".", 1)[0]
                    if root not in allowed_import_roots:
                        raise ImportError(f"import is not allowed in code runner: {{name}}")
                    return builtins.__import__(name, globals, locals, fromlist, level)

                safe_builtins = {{
                    "BaseException": BaseException,
                    "Exception": Exception,
                    "AssertionError": AssertionError,
                    "AttributeError": AttributeError,
                    "ImportError": ImportError,
                    "IndexError": IndexError,
                    "KeyError": KeyError,
                    "NameError": NameError,
                    "NotImplementedError": NotImplementedError,
                    "RuntimeError": RuntimeError,
                    "TypeError": TypeError,
                    "ValueError": ValueError,
                    "ZeroDivisionError": ZeroDivisionError,
                    "__build_class__": __build_class__,
                    "abs": abs,
                    "all": all,
                    "any": any,
                    "bin": bin,
                    "bool": bool,
                    "bytearray": bytearray,
                    "bytes": bytes,
                    "callable": callable,
                    "chr": chr,
                    "classmethod": classmethod,
                    "compile": compile,
                    "dict": dict,
                    "divmod": divmod,
                    "enumerate": enumerate,
                    "eval": eval,
                    "filter": filter,
                    "float": float,
                    "format": format,
                    "getattr": getattr,
                    "hasattr": hasattr,
                    "hex": hex,
                    "int": int,
                    "iter": iter,
                    "isinstance": isinstance,
                    "len": len,
                    "list": list,
                    "map": map,
                    "max": max,
                    "min": min,
                    "next": next,
                    "object": object,
                    "oct": oct,
                    "ord": ord,
                    "pow": pow,
                    "print": print,
                    "property": property,
                    "range": range,
                    "repr": repr,
                    "reversed": reversed,
                    "round": round,
                    "set": set,
                    "setattr": setattr,
                    "sorted": sorted,
                    "staticmethod": staticmethod,
                    "str": str,
                    "sum": sum,
                    "tuple": tuple,
                    "type": type,
                    "zip": zip,
                    "__import__": safe_import,
                }}
                namespace = {{
                    "__builtins__": safe_builtins,
                    "__name__": "__sandbox__",
                    "Any": typing.Any,
                    "Callable": typing.Callable,
                    "Dict": typing.Dict,
                    "List": typing.List,
                    "Literal": typing.Literal,
                    "Number": int | float,
                    "Optional": typing.Optional,
                    "Sequence": typing.Sequence,
                    "Set": typing.Set,
                    "Tuple": typing.Tuple,
                    "Union": typing.Union,
                    "FlowInterrupt": FlowInterrupt,
                    "ast": ast,
                    "capability": capability,
                    "json": json,
                    "math": math,
                    "typing": typing,
                }}
                namespace.update(build_sdk_namespaces())
                return namespace


            def infer_entrypoint(source):
                tree = ast.parse(source)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return node.name
                return None


            def artifact_key(request):
                manifest = request.get("capability_manifest") or {{}}
                key_payload = json.dumps(
                    {{
                        "language": request.get("language"),
                        "code": request.get("code"),
                        "entrypoint": request.get("entrypoint"),
                        "manifest_version": manifest.get("version"),
                    }},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                return hashlib.sha256(key_payload.encode("utf-8")).hexdigest()


            def validate_request(request):
                stage = "bootstrap"
                try:
                    source = str(request.get("code") or "")
                    stage = "parse"
                    tree = ast.parse(source)
                    entrypoint_name = request.get("entrypoint")
                    if not entrypoint_name:
                        for node in tree.body:
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                entrypoint_name = node.name
                                break
                    if not entrypoint_name:
                        raise RuntimeError("Entrypoint function not found: declare at least one function")
                    has_entrypoint = any(
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entrypoint_name
                        for node in tree.body
                    )
                    if not has_entrypoint:
                        raise RuntimeError(f"Entrypoint not found: {{entrypoint_name}}")

                    key = artifact_key(request)
                    compiled = compiled_cache.get(key)
                    if compiled is None:
                        stage = "compile"
                        compiled = compile(
                            source,
                            f"<sandbox:{{key}}>",
                            "exec",
                            flags=__future__.annotations.compiler_flag,
                            dont_inherit=True,
                        )
                        compiled_cache[key] = compiled
                    return {{"valid": True, "warnings": []}}
                except BaseException as exc:
                    context = request.get("context", {{}}) if isinstance(request, dict) else {{}}
                    return {{
                        "valid": False,
                        "error": {{
                            "language": request.get("language", "python") if isinstance(request, dict) else "python",
                            "service": {json.dumps(SERVICE_NAME)},
                            "stage": stage,
                            "message": str(exc),
                            "exception_type": type(exc).__name__,
                            "traceback": "".join(traceback.format_exception(exc)),
                            "request_id": context.get("request_id"),
                            "trace_id": context.get("trace_id"),
                        }},
                        "warnings": [],
                    }}


            def call_entrypoint(entrypoint, args, state):
                if current_request.get("kind") != "tool":
                    return entrypoint(args, state)
                signature = inspect.signature(entrypoint)
                parameters = [
                    param
                    for param in signature.parameters.values()
                    if param.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    )
                ]
                if len(parameters) >= 2 and parameters[0].name in ("args", "arguments") and parameters[1].name == "state":
                    return entrypoint(args, state)
                kwargs = dict(args)
                if "state" in signature.parameters:
                    kwargs["state"] = state
                return entrypoint(**kwargs)


            async def execute_one(raw_line):
                global current_request
                stage = "bootstrap"
                stdout_buffer = io.StringIO()
                stderr_buffer = io.StringIO()
                real_stdout = sys.stdout
                real_stderr = sys.stderr
                try:
                    current_request = json.loads(raw_line)
                    if "args" not in current_request and "state" not in current_request:
                        return json.dumps(validate_request(current_request), ensure_ascii=False, separators=(",", ":"))
                    state = _wrap_attr(dict(current_request["state"]))
                    current_request["state"] = state
                    args = _wrap_attr(dict(current_request["args"]))

                    key = artifact_key(current_request)
                    compiled = compiled_cache.get(key)
                    if compiled is None:
                        stage = "compile"
                        compiled = compile(
                            current_request["code"],
                            f"<sandbox:{{key}}>",
                            "exec",
                            flags=__future__.annotations.compiler_flag,
                            dont_inherit=True,
                        )
                        compiled_cache[key] = compiled

                    namespace = build_namespace()
                    namespace["variables"] = state.get("variables", {{}})
                    sys.stdout = stdout_buffer
                    sys.stderr = stderr_buffer
                    stage = "load"
                    exec(compiled, namespace)
                    entrypoint_name = current_request.get("entrypoint") or infer_entrypoint(current_request["code"])
                    if not entrypoint_name:
                        raise RuntimeError("Entrypoint function not found: declare at least one function")
                    entrypoint = namespace.get(entrypoint_name)
                    if not callable(entrypoint):
                        raise RuntimeError(f"Entrypoint not found: {{entrypoint_name}}")

                    stage = "user"
                    result = call_entrypoint(entrypoint, args, state)
                    if inspect.isawaitable(result):
                        result = await result
                    state_returned = result is state
                    response_payload = {{
                        "status": "completed",
                        "result": None if state_returned else result,
                        "state": state,
                        "state_returned": state_returned,
                        "logs": [],
                    }}
                except CapabilityInterrupt as interrupt:
                    payload = interrupt.payload
                    response_payload = {{
                        "status": "interrupted",
                        "result": payload.get("result"),
                        "state": current_request.get("state", {{}}),
                        "interrupt": payload.get("interrupt"),
                        "logs": [],
                    }}
                except FlowInterrupt as interrupt:
                    response_payload = {{
                        "status": "interrupted",
                        "result": None,
                        "state": current_request.get("state", {{}}),
                        "interrupt": {{
                            "kind": str(interrupt.body.get("kind", "user_message")),
                            "body": interrupt.body,
                        }},
                        "logs": [],
                    }}
                except BaseException as exc:
                    context = current_request.get("context", {{}}) if isinstance(current_request, dict) else {{}}
                    response_payload = {{
                        "status": "failed",
                        "result": None,
                        "state": current_request.get("state", {{}}) if isinstance(current_request, dict) else {{}},
                        "error": {{
                            "language": current_request.get("language", "python") if isinstance(current_request, dict) else "python",
                            "service": {json.dumps(SERVICE_NAME)},
                            "stage": stage,
                            "message": str(exc),
                            "exception_type": type(exc).__name__,
                            "traceback": "".join(traceback.format_exception(exc)),
                            "request_id": context.get("request_id"),
                            "trace_id": context.get("trace_id"),
                        }},
                        "logs": [],
                    }}
                finally:
                    sys.stdout = real_stdout
                    sys.stderr = real_stderr

                logs = response_payload.setdefault("logs", [])
                captured_stdout = stdout_buffer.getvalue().strip()
                captured_stderr = stderr_buffer.getvalue().strip()
                if captured_stdout:
                    logs.append({{"level": "info", "message": captured_stdout, "fields": {{"stream": "stdout"}}}})
                if captured_stderr:
                    logs.append({{"level": "warning", "message": captured_stderr, "fields": {{"stream": "stderr"}}}})
                return json.dumps(response_payload, ensure_ascii=False, separators=(",", ":"))


            async def main():
                real_stdout = sys.stdout
                while True:
                    raw_line = sys.stdin.readline()
                    if raw_line == "":
                        break
                    response = await execute_one(raw_line)
                    real_stdout.write(response + "\\n")
                    real_stdout.flush()


            current_request = {{}}

            if __name__ == "__main__":
                asyncio.run(main())
            """
        ).strip()
