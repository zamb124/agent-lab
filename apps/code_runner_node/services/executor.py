"""Node.js sandbox executor по контракту CodeExecutionRequest.

Целевой runtime: code-runner-node держит long-lived Node worker pool.
JS/TS source превращается в cached vm.Script по artifact-key, а каждый вызов
исполняется в свежем vm context с SDK capabilities.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import textwrap
import traceback
from pathlib import Path

from core.capabilities import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    code_execution_failed_response,
)
from core.config import get_settings
from core.tracing.operation_span import traced_operation

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"
SERVICE_NAME = "code_runner_node"
WORKER_POOL_ENV = "CODE_RUNNER_NODE_WORKERS"


class _NodeWorker:
    """Один persistent Node worker с JSON-lines IPC."""

    def __init__(self, *, node_bin: str, worker_path: Path, gateway_url: str):
        self._node_bin = node_bin
        self._worker_path = worker_path
        self._gateway_url = gateway_url
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None

    async def invoke(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        async with self._lock:
            process = await self._ensure_process()
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write(request.model_dump_json().encode("utf-8") + b"\n")
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
                    message="node sandbox exceeded wall time limit",
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
                    message="node sandbox worker exited without response",
                    exception_type="NodeSandboxWorkerExited",
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

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process
        self._process = await asyncio.create_subprocess_exec(
            self._node_bin,
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


class NodeSandboxExecutor:
    """Исполняет JavaScript/TypeScript user code через persistent Node worker pool."""

    def __init__(self) -> None:
        self._workers: list[_NodeWorker] = []
        self._next_worker = 0
        self._pool_lock = asyncio.Lock()
        self._runtime_dir = Path(tempfile.mkdtemp(prefix="code-runner-node-runtime-"))
        self._worker_path = self._runtime_dir / "node_worker.mjs"
        self._worker_path.write_text(self._worker_source(), encoding="utf-8")

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        if request.language not in ("javascript", "typescript"):
            return self._failed_response(
                request=request,
                stage="validation",
                message=f"code-runner-node cannot execute language={request.language}",
                exception_type="UnsupportedLanguageError",
            )

        async with traced_operation(
            "code_runner_node.execute",
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

    async def _select_worker(self) -> _NodeWorker:
        async with self._pool_lock:
            if not self._workers:
                node_bin = shutil.which("node")
                if node_bin is None:
                    raise RuntimeError("node executable is required for code-runner-node")
                gateway_url = get_settings().server.get_service_url("capability_gateway")
                count = self._worker_count()
                self._workers = [
                    _NodeWorker(node_bin=node_bin, worker_path=self._worker_path, gateway_url=gateway_url)
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

    def _worker_source(self) -> str:
        return textwrap.dedent(
            f"""
            import {{ createHash }} from 'node:crypto';
            import {{ createInterface }} from 'node:readline';
            import {{ stripTypeScriptTypes }} from 'node:module';
            import vm from 'node:vm';

            const gatewayUrl = process.argv[2];
            const capabilityCallPath = {json.dumps(CAPABILITY_CALL_PATH)};
            const scriptCache = new Map();

            class CapabilityInterrupt extends Error {{
              constructor(payload) {{
                super('Capability interrupt');
                this.name = 'CapabilityInterrupt';
                this.payload = payload;
              }}
            }}

            function inferEntrypoint(source) {{
              const candidates = [];
              const patterns = [
                /(?:export\\s+)?(?:async\\s+)?function\\s+([$A-Za-z_][$\\w]*)\\s*\\(/g,
                /(?:export\\s+)?(?:const|let|var)\\s+([$A-Za-z_][$\\w]*)\\s*=\\s*(?:async\\s*)?(?:\\([^)]*\\)|[$A-Za-z_][$\\w]*)\\s*=>/g,
              ];
              for (const pattern of patterns) {{
                for (const match of source.matchAll(pattern)) {{
                  candidates.push({{ index: match.index ?? 0, name: match[1] }});
                }}
              }}
              candidates.sort((a, b) => a.index - b.index);
              return candidates[0]?.name ?? null;
            }}

            function normalizeSource(request, entrypointName) {{
              let source = String(request.code ?? '');
              if (request.language === 'typescript') {{
                source = stripTypeScriptTypes(source, {{ mode: 'strip' }});
              }}
              source = source
                .replace(/^\\s*export\\s+(?=(async\\s+)?function|const|let|var|class)/gm, '')
                .replace(/^\\s*export\\s*\\{{[^}}]+\\}};?\\s*$/gm, '');
              return `${{source}}\\n\\nglobalThis.__entrypoint = ${{entrypointName}};\\n`;
            }}

            function artifactKey(request, entrypointName) {{
              const manifestVersion = request.capability_manifest?.version ?? '';
              return createHash('sha256')
                .update(JSON.stringify({{
                  language: request.language,
                  code: request.code,
                  entrypoint: entrypointName,
                  manifestVersion,
                }}))
                .digest('hex');
            }}

            function makeConsole(logs) {{
              const push = (level, values) => {{
                const message = values.map((value) => {{
                  if (typeof value === 'string') return value;
                  try {{ return JSON.stringify(value); }} catch {{ return String(value); }}
                }}).join(' ');
                if (message) logs.push({{ level, message, fields: {{ stream: 'console' }} }});
              }};
              return {{
                log: (...values) => push('info', values),
                info: (...values) => push('info', values),
                warn: (...values) => push('warning', values),
                error: (...values) => push('error', values),
              }};
            }}

            function installSdkNamespaces(sandbox, request, capability) {{
              const manifest = request.capability_manifest ?? {{}};
              const capabilities = Array.isArray(manifest.capabilities) ? manifest.capabilities : [];
              const namespaceMaps = new Map();
              for (const item of capabilities) {{
                if (!item || typeof item !== 'object' || typeof item.name !== 'string' || !item.name.includes('.')) continue;
                const [defaultNamespace, defaultMethod] = item.name.split('.', 2);
                const namespace = typeof item.sdk_namespace === 'string' && item.sdk_namespace.length > 0
                  ? item.sdk_namespace
                  : defaultNamespace;
                const method = typeof item.sdk_method === 'string' && item.sdk_method.length > 0
                  ? item.sdk_method
                  : defaultMethod;
                if (!namespaceMaps.has(namespace)) namespaceMaps.set(namespace, new Map());
                namespaceMaps.get(namespace).set(method, item.name);
              }}
              for (const [namespace, mapping] of namespaceMaps.entries()) {{
                sandbox[namespace] = new Proxy({{}}, {{
                  get(_target, prop) {{
                    if (typeof prop !== 'string') return undefined;
                    if (prop === 'then') return undefined;
                    if (prop === 'call') {{
                      return async (method, kwargs = {{}}) => capability(`${{namespace}}.${{method}}`, kwargs);
                    }}
                    const capabilityName = mapping.get(prop);
                    if (!capabilityName) {{
                      throw new Error(`Unknown capability method: ${{namespace}}.${{prop}}`);
                    }}
                    return async (kwargs = {{}}) => capability(capabilityName, kwargs);
                  }},
                }});
              }}
            }}

            async function executeOne(request) {{
              const logs = [];
              let stage = 'bootstrap';
              try {{
                const sourceForInference = String(request.code ?? '');
                const entrypointName = request.entrypoint || inferEntrypoint(sourceForInference);
                if (!entrypointName) {{
                  throw new Error('Entrypoint function not found: declare at least one function');
                }}

                stage = 'compile';
                const key = artifactKey(request, entrypointName);
                let script = scriptCache.get(key);
                if (!script) {{
                  const normalized = normalizeSource(request, entrypointName);
                  script = new vm.Script(normalized, {{ filename: `<sandbox:${{key}}>` }});
                  scriptCache.set(key, script);
                }}

                const capability = async (name, kwargs = {{}}) => {{
                  const headers = {{ 'Content-Type': 'application/json' }};
                  if (request.context?.request_id) headers['X-Request-Id'] = request.context.request_id;
                  if (request.context?.trace_id) headers['X-Trace-Id'] = request.context.trace_id;
                  const response = await fetch(`${{gatewayUrl}}${{capabilityCallPath}}`, {{
                    method: 'POST',
                    headers,
                    body: JSON.stringify({{
                      context: request.context,
                      name,
                      args: [],
                      kwargs,
                      state: request.state,
                    }}),
                  }});
                  if (!response.ok) {{
                    throw new Error(`Capability ${{name}} failed: ${{response.status}} ${{await response.text()}}`);
                  }}
                  const payload = await response.json();
                  if (payload.state && typeof payload.state === 'object' && !Array.isArray(payload.state)) {{
                    for (const key of Object.keys(request.state ?? {{}})) delete request.state[key];
                    Object.assign(request.state, payload.state);
                  }}
                  if (payload.status === 'interrupt') {{
                    throw new CapabilityInterrupt(payload);
                  }}
                  return payload.result;
                }};

                stage = 'user';
                const sandbox = {{
                  capability,
                  console: makeConsole(logs),
                  setTimeout,
                  clearTimeout,
                  Promise,
                }};
                installSdkNamespaces(sandbox, request, capability);
                const context = vm.createContext(sandbox, {{ name: 'code-runner-node-sandbox' }});
                script.runInContext(context, {{ timeout: Math.max(1, Number(request.wall_time_limit_seconds || 1)) * 1000 }});
                const entrypoint = context.__entrypoint;
                if (typeof entrypoint !== 'function') {{
                  throw new Error(`Entrypoint function not found: ${{entrypointName}}`);
                }}
                const state = request.state ?? {{}};
                const result = await entrypoint(request.args ?? {{}}, state);
                const stateReturned = result === state;
                return {{
                  status: 'completed',
                  result: stateReturned ? null : result,
                  state,
                  state_returned: stateReturned,
                  logs,
                }};
              }} catch (error) {{
                if (error instanceof CapabilityInterrupt) {{
                  return {{
                    status: 'interrupted',
                    result: error.payload?.result,
                    state: request.state ?? {{}},
                    interrupt: error.payload?.interrupt,
                    logs,
                  }};
                }}
                return {{
                  status: 'failed',
                  result: null,
                  state: request.state ?? {{}},
                  error: {{
                    language: request.language ?? 'javascript',
                    service: {json.dumps(SERVICE_NAME)},
                    stage,
                    message: error?.message ?? String(error),
                    exception_type: error?.name ?? 'Error',
                    traceback: error?.stack ?? String(error),
                    request_id: request.context?.request_id ?? null,
                    trace_id: request.context?.trace_id ?? null,
                  }},
                  logs,
                }};
              }}
            }}

            const rl = createInterface({{ input: process.stdin, crlfDelay: Infinity }});
            for await (const line of rl) {{
              if (!line) continue;
              let payload;
              try {{
                const request = JSON.parse(line);
                payload = await executeOne(request);
              }} catch (error) {{
                payload = {{
                  status: 'failed',
                  result: null,
                  state: {{}},
                  error: {{
                    language: 'javascript',
                    service: {json.dumps(SERVICE_NAME)},
                    stage: 'bootstrap',
                    message: error?.message ?? String(error),
                    exception_type: error?.name ?? 'Error',
                    traceback: error?.stack ?? String(error),
                  }},
                  logs: [],
                }};
              }}
              process.stdout.write(JSON.stringify(payload) + '\\n');
            }}
            """
        ).strip()
