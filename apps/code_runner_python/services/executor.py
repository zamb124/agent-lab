"""Python sandbox executor по контракту CodeExecutionRequest.

Целевой runtime: code-runner-python держит пул долгоживущих worker-ов.
Worker компилирует исходный код один раз по artifact-key и дальше исполняет
закэшированный code object в свежем sandbox namespace на каждый вызов.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import shutil
import subprocess
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
    verify_execution_context,
)
from core.capabilities.runner_cache import code_runner_python_sandbox_site, sandbox_cache_lock
from core.capabilities.runner_pool import code_runner_pool_size
from core.capabilities.sandbox_libraries import (
    PYTHON_ALLOWED_IMPORT_ROOTS,
    PYTHON_FORBIDDEN_BUILTIN_NAMES,
    PYTHON_FORBIDDEN_IMPORT_ROOTS,
    PYTHON_SANDBOX_BUILTINS,
)
from core.config import get_settings
from core.tracing.operation_span import traced_operation

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"
SERVICE_NAME = "code_runner_python"
WORKER_IPC_STREAM_LIMIT_BYTES = 64 * 1024 * 1024
_SANDBOX_REQUIREMENTS = Path(__file__).resolve().parents[1] / "sandbox-requirements.txt"


def ensure_python_sandbox_site() -> Path:
    """Ставит pandas/numpy/yaml/openpyxl в отдельный target, не в platform venv."""
    cache_root = code_runner_python_sandbox_site()
    requirements_text = _SANDBOX_REQUIREMENTS.read_text(encoding="utf-8")
    digest = hashlib.sha256(requirements_text.encode("utf-8")).hexdigest()
    marker = cache_root / ".requirements.sha256"
    pandas_dir = cache_root / "pandas"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest and pandas_dir.is_dir():
        return cache_root
    with sandbox_cache_lock(cache_root):
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest and pandas_dir.is_dir():
            return cache_root
        if cache_root.exists():
            shutil.rmtree(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True)
        uv_bin = shutil.which("uv")
        if uv_bin is None:
            raise RuntimeError("uv is required to install python sandbox site-packages")
        completed = subprocess.run(
            [
                uv_bin,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--target",
                str(cache_root),
                "-r",
                str(_SANDBOX_REQUIREMENTS),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"python sandbox site-packages install failed: {completed.stderr}")
        _ = marker.write_text(digest, encoding="utf-8")
    return cache_root


class _PythonWorker:
    """Один долгоживущий Python sandbox worker с JSON-lines IPC."""

    def __init__(self, *, worker_path: Path, gateway_url: str, sandbox_site: Path):
        self._worker_path: Path = worker_path
        self._gateway_url: str = gateway_url
        self._sandbox_site: Path = sandbox_site
        self._lock: asyncio.Lock = asyncio.Lock()
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
            except asyncio.CancelledError:
                await asyncio.shield(self._restart())
                raise
            except TimeoutError as exc:
                await asyncio.shield(self._restart())
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="timeout",
                    message="python sandbox exceeded wall time limit",
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            except Exception as exc:
                await asyncio.shield(self._restart())
                return code_execution_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            if not line:
                await asyncio.shield(self._restart())
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
                await asyncio.shield(self._restart())
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
            except asyncio.CancelledError:
                await asyncio.shield(self._restart())
                raise
            except TimeoutError as exc:
                await asyncio.shield(self._restart())
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="timeout",
                    message="python sandbox validation exceeded wall time limit",
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            except Exception as exc:
                await asyncio.shield(self._restart())
                return code_validation_failed_response(
                    request,
                    service=SERVICE_NAME,
                    stage="worker_ipc",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            if not line:
                await asyncio.shield(self._restart())
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
                await asyncio.shield(self._restart())
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
            str(self._sandbox_site),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=WORKER_IPC_STREAM_LIMIT_BYTES,
        )
        return self._process

    async def _restart(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(TimeoutError):
            _ = await asyncio.wait_for(process.wait(), timeout=2.0)
            return
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(TimeoutError):
            _ = await asyncio.wait_for(process.wait(), timeout=2.0)

    async def close(self) -> None:
        await self._restart()


class PythonSandboxExecutor:
    """Исполняет пользовательский Python-код через пул долгоживущих sandbox worker-ов."""

    def __init__(self) -> None:
        self._workers: list[_PythonWorker] = []
        self._idle_workers: asyncio.Queue[_PythonWorker] = asyncio.Queue()
        self._pool_lock: asyncio.Lock = asyncio.Lock()
        self._runtime_dir: Path = Path(tempfile.mkdtemp(prefix="code-runner-python-runtime-"))
        self._worker_path: Path = self._runtime_dir / "python_worker.py"
        self._sandbox_site: Path = ensure_python_sandbox_site()
        _ = self._worker_path.write_text(self._worker_source(), encoding="utf-8")

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        security_error = self._verify_execution_request(request)
        if security_error is not None:
            return security_error
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
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            try:
                worker = await self._acquire_worker()
            except Exception as exc:
                return self._failed_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            try:
                return await worker.invoke(request)
            except Exception as exc:
                return self._failed_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            finally:
                self._release_worker(worker)

    async def validate(self, request: CodeValidationRequest) -> CodeValidationResponse:
        security_error = self._verify_validation_request(request)
        if security_error is not None:
            return security_error
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
                "platform.code_runner.sandbox_profile": request.sandbox.profile,
                "platform.code_runner.sandbox_memory_limit_mb": request.sandbox.limits.memory_limit_mb,
                "platform.code_runner.sandbox_network": request.sandbox.network.mode,
            },
        ):
            try:
                worker = await self._acquire_worker()
            except Exception as exc:
                return self._failed_validation_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            try:
                return await worker.validate(request)
            except Exception as exc:
                return self._failed_validation_response(
                    request=request,
                    stage="runtime",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text="".join(traceback.format_exception(exc)),
                )
            finally:
                self._release_worker(worker)

    async def _acquire_worker(self) -> _PythonWorker:
        """Берёт первый свободный worker из очереди.

        Очередь свободных worker-ов вместо round-robin: длинный запрос не блокирует
        запросы, которые round-robin назначил бы на тот же worker (head-of-line blocking).
        """
        async with self._pool_lock:
            if not self._workers:
                gateway_url = get_settings().server.get_service_url("capability_gateway")
                count = self._worker_count()
                self._workers = [
                    _PythonWorker(
                        worker_path=self._worker_path,
                        gateway_url=gateway_url,
                        sandbox_site=self._sandbox_site,
                    )
                    for _ in range(count)
                ]
                for pooled_worker in self._workers:
                    self._idle_workers.put_nowait(pooled_worker)
        return await self._idle_workers.get()

    def _release_worker(self, worker: _PythonWorker) -> None:
        self._idle_workers.put_nowait(worker)

    def _worker_count(self) -> int:
        return code_runner_pool_size("python")

    async def aclose(self) -> None:
        workers = list(self._workers)
        self._workers = []
        _ = await asyncio.gather(*(worker.close() for worker in workers), return_exceptions=True)
        shutil.rmtree(self._runtime_dir, ignore_errors=True)

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
            import types
            import typing
            import urllib.error
            import urllib.request

            gateway_url = sys.argv[1]
            sandbox_site = sys.argv[2]
            if sandbox_site:
                sys.path.insert(0, sandbox_site)
            capability_call_path = {json.dumps(CAPABILITY_CALL_PATH)}
            compiled_cache = {{}}
            base_allowed_import_roots = set({json.dumps(sorted(PYTHON_ALLOWED_IMPORT_ROOTS))})
            forbidden_import_roots = set({json.dumps(sorted(PYTHON_FORBIDDEN_IMPORT_ROOTS))})
            forbidden_builtin_names = set({json.dumps(sorted(PYTHON_FORBIDDEN_BUILTIN_NAMES))})
            sandbox_builtin_names = {json.dumps([name for name in PYTHON_SANDBOX_BUILTINS if name != "FlowInterrupt"])}
            installed_sdk_modules = set()
            pathlib_locked = False


            class SandboxPolicyViolation(PermissionError):
                pass


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


            class ExecutionStateView(dict):
                # Контракт state inline-кода: атрибутный доступ к ключам поверх dict
                # (state.session_id и state["session_id"] — один объект), как у
                # in-process ExecutionState и у объекта state в JS-runner.
                def __getattr__(self, name):
                    try:
                        return self[name]
                    except KeyError:
                        raise AttributeError(f"state has no field: {{name}}") from None

                def __setattr__(self, name, value):
                    self[name] = value

                def __delattr__(self, name):
                    try:
                        del self[name]
                    except KeyError:
                        raise AttributeError(f"state has no field: {{name}}") from None


            def manifest_capability_names():
                manifest = current_request.get("capability_manifest") or {{}}
                capabilities = manifest.get("capabilities") or []
                names = set()
                for item in capabilities:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if isinstance(name, str) and name:
                        names.add(name)
                return names


            async def capability(capability_name, **kwargs):
                if capability_name not in manifest_capability_names():
                    raise SandboxPolicyViolation(
                        f"Capability is not declared in manifest: {{capability_name}}"
                    )
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
                    # Один tool/capability (read_file + page_summarizations) может идти
                    # дольше минуты; лимит = wall_time ноды, не хардкод 120s.
                    capability_timeout = float(
                        current_request.get("wall_time_limit_seconds") or 0
                    )
                    if capability_timeout <= 0:
                        raise RuntimeError(
                            "Capability call requires positive wall_time_limit_seconds"
                        )
                    with urllib.request.urlopen(
                        http_request, timeout=capability_timeout
                    ) as response:
                        response_body = response.read()
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Capability {{capability_name}} failed: {{exc.code}} {{error_body}}"
                    ) from exc
                decoded = json.loads(response_body.decode("utf-8"))
                platform_effects = decoded.get("platform_effects")
                if platform_effects is not None:
                    if not isinstance(platform_effects, list):
                        raise RuntimeError(
                            f"Capability {{capability_name}} returned invalid platform_effects"
                        )
                    current_request.setdefault("_platform_effects", []).extend(
                        platform_effects
                    )
                returned_state = decoded.get("state")
                if isinstance(returned_state, dict):
                    current_request["state"].clear()
                    current_request["state"].update(returned_state)
                if decoded.get("status") == "interrupt":
                    raise CapabilityInterrupt(decoded)
                return decoded.get("result")


            def sdk_call_factory(capability_name):
                async def sdk_call(**kwargs):
                    return await capability(capability_name, **kwargs)

                return sdk_call


            def sdk_namespace_call_factory(namespace, mapping):
                async def namespace_call(method, **kwargs):
                    if namespace == "tools":
                        if not isinstance(method, str) or not method:
                            raise AttributeError("Tool capability method must be a non-empty string")
                        capability_name = f"tools.{{method}}"
                    else:
                        capability_name = mapping.get(method)
                        if capability_name is None:
                            raise AttributeError(f"Unknown capability method: {{namespace}}.{{method}}")
                    return await capability(capability_name, **kwargs)

                return namespace_call


            def build_capability_namespace(namespace, mapping):
                attributes = {{
                    "call": sdk_namespace_call_factory(namespace, dict(mapping)),
                }}
                for method, capability_name in mapping.items():
                    if method == "call":
                        raise SandboxPolicyViolation(
                            f"Capability SDK method name is reserved: {{namespace}}.{{method}}"
                        )
                    attributes[method] = sdk_call_factory(capability_name)
                return types.SimpleNamespace(**attributes)


            def build_sdk_namespaces():
                return build_sdk_namespaces_from(current_request)


            def is_allowed_import(name, extra_roots):
                if not name:
                    return False
                if name.split(".", 1)[0] in forbidden_import_roots:
                    return False
                if name in forbidden_import_roots:
                    return False
                allowed = base_allowed_import_roots | extra_roots
                parts = name.split(".")
                for index in range(len(parts), 0, -1):
                    prefix = ".".join(parts[:index])
                    if prefix in allowed:
                        return True
                    if prefix in forbidden_import_roots:
                        return False
                return False


            def lock_pathlib(module):
                global pathlib_locked
                if pathlib_locked:
                    return module
                Path = module.Path

                def blocked(self, *args, **kwargs):
                    raise PermissionError(
                        "pathlib filesystem access is not allowed; use files.*"
                    )

                for method_name in (
                    "read_text", "read_bytes", "write_text", "write_bytes", "open",
                    "unlink", "mkdir", "rmdir", "iterdir", "glob", "rglob", "stat",
                    "exists", "is_file", "is_dir", "touch", "rename", "replace",
                    "chmod", "absolute", "resolve", "cwd", "home",
                ):
                    setattr(Path, method_name, blocked)
                pathlib_locked = True
                return module


            def install_sdk_modules(namespaces):
                for name in list(installed_sdk_modules):
                    sys.modules.pop(name, None)
                installed_sdk_modules.clear()
                modules = {{}}
                for name, obj in namespaces.items():
                    module = types.ModuleType(name)
                    for attr, value in vars(obj).items():
                        setattr(module, attr, value)
                    sys.modules[name] = module
                    installed_sdk_modules.add(name)
                    modules[name] = module
                return modules


            def sdk_namespace_names(request):
                manifest = request.get("capability_manifest") or {{}}
                capabilities = manifest.get("capabilities") or []
                names = set()
                for item in capabilities:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) or "." not in name:
                        continue
                    namespace = item.get("sdk_namespace")
                    if not isinstance(namespace, str) or not namespace:
                        namespace = name.split(".", 1)[0]
                    names.add(namespace)
                return names


            def build_sdk_namespaces_from(request):
                manifest = request.get("capability_manifest") or {{}}
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
                    namespace: build_capability_namespace(namespace, mapping)
                    for namespace, mapping in namespace_maps.items()
                }}


            def build_namespace():
                sdk_modules = install_sdk_modules(build_sdk_namespaces())
                extra_roots = set(installed_sdk_modules)

                def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
                    if level != 0:
                        raise ImportError("relative imports are not allowed in code runner")
                    if not is_allowed_import(name, extra_roots):
                        raise ImportError(f"import is not allowed in code runner: {{name}}")
                    root = name.split(".", 1)[0]
                    if name in installed_sdk_modules:
                        return sys.modules[name]
                    if root in installed_sdk_modules:
                        return sys.modules[root]
                    module = builtins.__import__(name, globals, locals, fromlist, level)
                    if name == "pathlib" or name.startswith("pathlib."):
                        lock_pathlib(sys.modules["pathlib"])
                    return module

                safe_builtins = {{name: getattr(builtins, name) for name in sandbox_builtin_names}}
                safe_builtins["__import__"] = safe_import
                safe_builtins["__build_class__"] = __build_class__
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
                namespace.update(sdk_modules)
                return namespace


            def infer_entrypoint(source):
                tree = ast.parse(source)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return node.name
                return None


            def validate_sandbox_source(tree):
                extra_roots = sdk_namespace_names(current_request)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if not is_allowed_import(alias.name, extra_roots):
                                raise SandboxPolicyViolation(
                                    f"import is not allowed in code runner: {{alias.name}}"
                                )
                    elif isinstance(node, ast.ImportFrom):
                        if node.level != 0:
                            raise SandboxPolicyViolation("relative imports are not allowed in code runner")
                        module = node.module or ""
                        if not is_allowed_import(module, extra_roots):
                            raise SandboxPolicyViolation(
                                f"import is not allowed in code runner: {{module}}"
                            )
                    elif isinstance(node, ast.Name):
                        if node.id in forbidden_builtin_names:
                            raise SandboxPolicyViolation(
                                f"builtin is not allowed in code runner: {{node.id}}"
                            )
                        if node.id.startswith("__") and node.id.endswith("__"):
                            raise SandboxPolicyViolation(
                                f"dunder name is not allowed in code runner: {{node.id}}"
                            )
                    elif isinstance(node, ast.Attribute):
                        if node.attr in forbidden_builtin_names:
                            raise SandboxPolicyViolation(
                                f"attribute is not allowed in code runner: {{node.attr}}"
                            )
                        if node.attr.startswith("__") and node.attr.endswith("__"):
                            raise SandboxPolicyViolation(
                                f"dunder attribute is not allowed in code runner: {{node.attr}}"
                            )


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
                    validate_sandbox_source(tree)
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
                        tree = ast.parse(source)
                        validate_sandbox_source(tree)
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
                    current_request["_platform_effects"] = []
                    state = ExecutionStateView(current_request["state"])
                    current_request["state"] = state
                    args = dict(current_request["args"])

                    key = artifact_key(current_request)
                    compiled = compiled_cache.get(key)
                    if compiled is None:
                        stage = "compile"
                        tree = ast.parse(current_request["code"])
                        validate_sandbox_source(tree)
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
                        "platform_effects": current_request["_platform_effects"],
                    }}
                except CapabilityInterrupt as interrupt:
                    payload = interrupt.payload
                    response_payload = {{
                        "status": "interrupted",
                        "result": payload.get("result"),
                        "state": current_request.get("state", {{}}),
                        "interrupt": payload.get("interrupt"),
                        "logs": [],
                        "platform_effects": current_request.get("_platform_effects", []),
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
                        "platform_effects": current_request.get("_platform_effects", []),
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
                        "platform_effects": current_request.get("_platform_effects", []),
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
