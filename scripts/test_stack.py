"""
Супервизор тестового стека сервисов платформы — единственный владелец процессов.

`make test-up` вызывает `test_stack.py up`: параллельно стартует все granian
HTTP-сервисы и TaskIQ-воркеры, параллельно ждёт их readiness и пишет манифест
`/tmp/platform_test_stack.json`. pytest-воркеры процессы не стартуют и не
убивают — фикстуры в `tests/fixtures/services.py` только проверяют готовность.

Команды:
    uv run python -m scripts.test_stack up
    uv run python -m scripts.test_stack down
    uv run python -m scripts.test_stack status

Логи процессов: /tmp/platform_test_stack/<name>.log / <name>.err
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import redis
import redis.exceptions as redis_exceptions

from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityManifest,
    CodeExecutionRequest,
    execution_token_exp,
    issue_execution_token,
    locked_down_code_sandbox_policy,
)
from core.test_scope import TEST_SCOPE_DEFAULT_ENV, TEST_SCOPE_STATIC_E2E
from core.types import JsonObject, JsonValue, require_json_object, require_json_value
from tests.fixtures.test_database_env import (
    TEST_DATABASE_ENV,
    TEST_LIVEKIT_API_SECRET,
    TEST_OFFICE_JWT_SECRET,
    load_openfga_test_env_overlay,
)

STACK_MANIFEST_PATH = Path("/tmp/platform_test_stack.json")
STACK_LOG_DIR = Path("/tmp/platform_test_stack")
BASELINE_PYTEST_WORKERS = 10
# Parallel spawn of granian + TaskIQ: import under ~100 processes takes ~2 min.
# 90–120 s expire while late processes are still importing.
STACK_READINESS_TIMEOUT_SEC = 180.0

_TASKIQ_REDIS_URL = "redis://localhost:63792/1"
_TASKIQ_CONSUMER_GROUP = "taskiq"

# Общие env переменные для всех сервисов стека (те же БД, что в conftest и миграциях).
COMMON_TEST_ENV: dict[str, str] = {
    **TEST_DATABASE_ENV,
    "TESTING": "true",
    "PYTHONUNBUFFERED": "1",
    # Статический scope для запросов без X-Test-Scope (браузер/Electron в E2E-фазах -n0).
    TEST_SCOPE_DEFAULT_ENV: TEST_SCOPE_STATIC_E2E,
    "DATABASE__REDIS_URL": "redis://localhost:63792/0",
    "TASKS__BROKER_URL": "redis://localhost:63792/1",
    # DevInterServiceProxy: браузер на :9021 с путём /flows/... → flows_service_url (см. dev_inter_service_proxy.mdc).
    "SERVER__ENV": "test",
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "SERVER__FLOWS_SERVICE_URL": "http://localhost:9001",
    "SERVER__RAG_SERVICE_URL": "http://localhost:9002",
    "SERVER__CRM_SERVICE_URL": "http://localhost:9003",
    "SERVER__FRONTEND_SERVICE_URL": "http://localhost:9004",
    "SERVER__SYNC_SERVICE_URL": "http://localhost:9005",
    "SERVER__SEARCH_SERVICE_URL": "http://localhost:9010",
    "SERVER__VOICE_SERVICE_URL": "http://localhost:9015",
    "SERVER__PROVIDER_LITSERVE_SERVICE_URL": "http://localhost:9014",
    "SERVER__CAPABILITY_GATEWAY_SERVICE_URL": "http://localhost:9016",
    "SERVER__CODE_RUNNER_PYTHON_SERVICE_URL": "http://localhost:9017",
    "SERVER__CODE_RUNNER_NODE_SERVICE_URL": "http://localhost:9018",
    "SERVER__CODE_RUNNER_GO_SERVICE_URL": "http://localhost:9019",
    "SERVER__CODE_RUNNER_CSHARP_SERVICE_URL": "http://localhost:9020",
    "SERVER__WORKTRACKER_SERVICE_URL": "http://localhost:9021",
    "SERVER__SECRETS_SERVICE_URL": "http://localhost:9022",
    "SERVER__OFFICE_SERVICE_URL": "http://localhost:9008",
    "OFFICE__JWT_SECRET": TEST_OFFICE_JWT_SECRET,
    "OFFICE__DOCUMENT_SERVER_PUBLIC_URL": "http://localhost:18088",
    "OFFICE__CALLBACK_PUBLIC_BASE_URL": "http://host.docker.internal:9008",
    "SERVER__DOCUMENT_SERVER_DEV_UPSTREAM_URL": "http://localhost:18088",
    "VOICE__STT__PROVIDER": "mock",
    "VOICE__STT__MOCK_TRANSCRIPT_TEXT": "Тестовая транскрипция sync worker",
    "CALLS__LIVEKIT_URL": "ws://localhost:7890",
    "CALLS__LIVEKIT_PUBLIC_URL": "http://localhost:7890",
    "CALLS__LIVEKIT_API_KEY": "devkey",
    "CALLS__LIVEKIT_API_SECRET": TEST_LIVEKIT_API_SECRET,
    "S3__ENABLED": "true",
    "S3__DEFAULT_BUCKET": "test-bucket",
    "S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL": "http://localhost:19002",
    "S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID": "minioadmin",
    "S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY": "minioadmin",
    "S3__BUCKETS__TEST-BUCKET__REGION_NAME": "us-east-1",
    "S3__BUCKETS__TEST-BUCKET__PROVIDER": "minio",
    "S3__BUCKETS__TEST_BUCKET__ENDPOINT_URL": "http://localhost:19002",
    "S3__BUCKETS__TEST_BUCKET__ACCESS_KEY_ID": "minioadmin",
    "S3__BUCKETS__TEST_BUCKET__SECRET_ACCESS_KEY": "minioadmin",
    "S3__BUCKETS__TEST_BUCKET__REGION_NAME": "us-east-1",
    "S3__BUCKETS__TEST_BUCKET__PROVIDER": "minio",
    "PUSH__ENABLED": "true",
    "PUSH__VAPID_PUBLIC_KEY": "BP1OB4uP0WSgQqumAOefg1PdsN9S7qA1-UK26qjSPa11ylB1HgbcrVi6peEUkhkdfrADeTa_dwypXYiucfbu3JQ",
    "PUSH__VAPID_PRIVATE_KEY": "lwzkecdrLZYcyUVhYUQuAnXYk92xup132qCCk5BtUEs",
    "PUSH__VAPID_EMAIL": "test@humanitec.ru",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    "RAG__EMBEDDING__PROVIDER": "provider_litserve",
    "RAG__EMBEDDING__API__MODEL": "qwen/qwen3-embedding-0.6b",
    "RAG__EMBEDDING__API__DIMENSION": "1024",
    "RAG__EMBEDDING__API__MRL_OUTPUT_DIMENSION": "1024",
    "PROVIDER_LITSERVE__API__BASE_URL": "http://localhost:9014/v1",
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
}


@dataclass(frozen=True)
class GranianService:
    """HTTP-сервис стека: granian + ASGI app + readiness по /health."""

    name: str
    app_path: str
    port: int
    readiness_timeout: float
    env: dict[str, str] = field(default_factory=dict)
    readiness_path: str = "/health"
    workers: int = 1


@dataclass(frozen=True)
class TaskiqWorkerService:
    """TaskIQ-воркер стека: readiness — живой consumer в группе taskiq стрима."""

    name: str
    worker_module: str
    stream_name: str
    workers: int
    readiness_timeout: float
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExternalReadiness:
    """Внешний процесс (docker-compose), для которого стек только ждёт readiness."""

    name: str
    url: str
    readiness_timeout: float


def _bootstrap_parent_test_env() -> None:
    """Probe-токены подписываются в родительском процессе test_stack — env как у дочерних сервисов."""
    import core.config.base

    os.environ.setdefault("TESTING", "true")
    for key, value in TEST_DATABASE_ENV.items():
        os.environ.setdefault(key, value)
    core.config.base._settings_instance = None


def resolve_pytest_workers() -> int:
    raw = os.environ.get("WORKERS", "10").strip()
    if raw == "auto":
        return BASELINE_PYTEST_WORKERS
    return int(raw)


def stack_scale_factor(pytest_workers: int | None = None) -> float:
    workers = pytest_workers if pytest_workers is not None else resolve_pytest_workers()
    if workers <= BASELINE_PYTEST_WORKERS:
        return 1.0
    return workers / BASELINE_PYTEST_WORKERS


def scale_stack_workers(baseline: int, pytest_workers: int | None = None) -> int:
    workers = pytest_workers if pytest_workers is not None else resolve_pytest_workers()
    if workers <= BASELINE_PYTEST_WORKERS:
        return baseline
    return max(baseline, math.ceil(baseline * workers / BASELINE_PYTEST_WORKERS))


def _scaled_code_runner_python_workers(pytest_workers: int | None = None) -> int:
    return scale_stack_workers(12, pytest_workers)


def _test_flows_worker_concurrency(pytest_workers: int | None = None) -> int:
    """Параллельные process_flow_task: OCC ledger per-session, не глобальный lock.

    Раньше при WORKERS>1 оставляли 1 consumer «против гонок projection hash».
    Это сериализовало все A2A (включая CRM note-analyze) в одну очередь: под
    -n10 SendMessage collect ждёт, пока единственный worker доест чужие графы,
    CRM-задача остаётся running без error до poll 90 с. Hash mismatch —
    per session_id; разные context_id не делят head. Baseline 8.
    """
    return scale_stack_workers(8, pytest_workers)


def build_granian_services(pytest_workers: int | None = None) -> tuple[GranianService, ...]:
    code_runner_workers = _scaled_code_runner_python_workers(pytest_workers)
    return (
    GranianService(
        name="secrets",
        app_path="apps.secrets.main:app",
        port=9022,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=scale_stack_workers(4, pytest_workers),
    ),
    GranianService(
        name="flows",
        app_path="apps.flows.main:app",
        port=9001,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=scale_stack_workers(14, pytest_workers),
    ),
    GranianService(name="rag", app_path="apps.rag.main:app", port=9002, readiness_timeout=STACK_READINESS_TIMEOUT_SEC),
    GranianService(
        name="crm",
        app_path="apps.crm.main:app",
        port=9003,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=scale_stack_workers(8, pytest_workers),
    ),
    GranianService(
        name="frontend",
        app_path="apps.frontend.main:app",
        port=9004,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        env={
            "HOSTNAME": "frontend-e2e-pod",
            "AGENT_LLM_PROXY_USE_MOCK_AUTO": "1",
        },
    ),
    GranianService(name="sync", app_path="apps.sync.main:app", port=9005, readiness_timeout=STACK_READINESS_TIMEOUT_SEC),
    GranianService(name="office", app_path="apps.office.main:app", port=9008, readiness_timeout=STACK_READINESS_TIMEOUT_SEC),
    GranianService(
        name="search",
        app_path="apps.search.main:app",
        port=9010,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=scale_stack_workers(2, pytest_workers),
        env={
            "SEARCH__TINYFISH__API_KEY": "",
            "SEARCH__TINYFISH__ENABLED": "false",
            "SEARCH__LINKUP__API_KEY": "",
            "SEARCH__LINKUP__ENABLED": "false",
            "SEARCH__SERPER__API_KEY": "",
            "SEARCH__SERPER__ENABLED": "false",
            "SEARCH__PROVIDER_STATE_KEY_PREFIX": "test:search:providers:stack",
            "SEARCH__UNAVAILABLE_TTL_SECONDS": "30",
            "CRAWL__BOOTSTRAP_TRANCO_ON_EMPTY": "false",
        },
    ),
    GranianService(
        name="provider_litserve",
        app_path="apps.provider_litserve.main:app",
        port=9014,
        readiness_timeout=240.0,
        env={
            "PROVIDER_LITSERVE__INFRA__BACKEND": "placeholder",
            "PROVIDER_LITSERVE__INFRA__ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__EMBEDDING_ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__RERANK_ACCELERATOR": "cpu",
            "PROVIDER_LITSERVE__INFRA__GATEWAY_PORT": "9014",
            "PROVIDER_LITSERVE__INFRA__SQLITE_PATH": "/tmp/platform_test_provider_litserve_registry.db",
        },
    ),
    GranianService(name="voice", app_path="apps.voice.main:app", port=9015, readiness_timeout=STACK_READINESS_TIMEOUT_SEC),
    GranianService(
        name="capability_gateway",
        app_path="apps.capability_gateway.main:app",
        port=9016,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=scale_stack_workers(6, pytest_workers),
    ),
    GranianService(
        name="code_runner_python",
        app_path="apps.code_runner_python.main:app",
        port=9017,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=code_runner_workers,
        env={
            "CODE_RUNNER_PYTHON_WORKERS": str(code_runner_workers),
        },
    ),
    GranianService(
        name="code_runner_node",
        app_path="apps.code_runner_node.main:app",
        port=9018,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=code_runner_workers,
        env={
            "CODE_RUNNER_NODE_WORKERS": str(code_runner_workers),
        },
    ),
    GranianService(
        name="code_runner_go",
        app_path="apps.code_runner_go.main:app",
        port=9019,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=code_runner_workers,
        env={
            "CODE_RUNNER_GO_WORKERS": str(code_runner_workers),
        },
    ),
    GranianService(
        name="code_runner_csharp",
        app_path="apps.code_runner_csharp.main:app",
        port=9020,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        workers=code_runner_workers,
        env={
            "CODE_RUNNER_CSHARP_WORKERS": str(code_runner_workers),
        },
    ),
    GranianService(
        name="worktracker",
        app_path="apps.worktracker.main:app",
        port=9021,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    GranianService(
        name="wiki",
        app_path="apps.wiki.main:app",
        port=9023,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    GranianService(
        name="guest_runtime",
        app_path="apps.guest_runtime.main:app",
        port=9024,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        env={
            "GUEST_RUNTIME__EXECUTOR": "inprocess",
            "GUEST_RUNTIME__MAX_LEASES_PER_COMPANY": "32",
            "GUEST_RUNTIME__MAX_LEASES_CLUSTER": "128",
        },
    ),
)


def build_taskiq_worker_services(pytest_workers: int | None = None) -> tuple[TaskiqWorkerService, ...]:
    return (
    TaskiqWorkerService(
        name="flows_worker",
        worker_module="apps.flows_worker.worker:worker_app",
        stream_name="flows_worker",
        workers=_test_flows_worker_concurrency(pytest_workers),
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    TaskiqWorkerService(
        name="rag_worker",
        worker_module="apps.rag_worker.worker:worker_app",
        stream_name="rag",
        workers=1,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    TaskiqWorkerService(
        name="search_worker",
        worker_module="apps.search_worker.worker:worker_app",
        stream_name="search",
        workers=scale_stack_workers(2, pytest_workers),
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        env={
            "CRAWL__MIN_EXTRACT_CHARS": "50",
            "CRAWL__BOOTSTRAP_TRANCO_ON_EMPTY": "false",
        },
    ),
    TaskiqWorkerService(
        name="sync_worker",
        worker_module="apps.sync_worker.worker:worker_app",
        stream_name="sync",
        workers=scale_stack_workers(2, pytest_workers),
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
        env={
            "SERVER__SYNC_SERVICE_URL": "http://127.0.0.1:9005",
            "CALLS__SPEECH_TO_CHAT__SEGMENT_SECONDS": "2",
            "CALLS__SPEECH_TO_CHAT__POLL_INITIAL_DELAY_SECONDS": "0.5",
            "CALLS__SPEECH_TO_CHAT__POLL_INTERVAL_SECONDS": "1",
        },
    ),
    TaskiqWorkerService(
        name="crm_worker",
        worker_module="apps.crm_worker.worker:worker_app",
        stream_name="crm",
        workers=scale_stack_workers(16, pytest_workers),
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    TaskiqWorkerService(
        name="crm_summary_worker",
        worker_module="apps.crm_worker.summary_worker:worker_app",
        stream_name="crm_summary",
        workers=scale_stack_workers(2, pytest_workers),
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    TaskiqWorkerService(
        name="idle_worker",
        worker_module="apps.idle_worker.worker:worker_app",
        stream_name="idle",
        workers=1,
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
    )


def _stack_capacity_snapshot(
    granian_services: tuple[GranianService, ...],
    taskiq_services: tuple[TaskiqWorkerService, ...],
) -> dict[str, int]:
    capacity: dict[str, int] = {}
    for service in granian_services:
        capacity[service.name] = service.workers
    for service in taskiq_services:
        capacity[service.name] = service.workers
    return capacity


EXTERNAL_READINESS: tuple[ExternalReadiness, ...] = (
    ExternalReadiness(
        name="test-a2a-agent",
        url="http://localhost:18052/health",
        readiness_timeout=STACK_READINESS_TIMEOUT_SEC,
    ),
)


def _build_process_env(service_env: dict[str, str]) -> dict[str, str]:
    process_env: dict[str, str] = {
        **os.environ,
        **COMMON_TEST_ENV,
        **load_openfga_test_env_overlay(),
        **service_env,
    }
    process_env.pop("PYTEST_XDIST_WORKER", None)
    process_env.pop("PYTEST_XDIST_WORKER_COUNT", None)
    return process_env


def _granian_command(service: GranianService) -> list[str]:
    return [
        sys.executable,
        "-m",
        "granian",
        "--interface",
        "asgi",
        service.app_path,
        "--host",
        "127.0.0.1",
        "--port",
        str(service.port),
        "--http",
        "auto",
        "--ws",
        "--workers",
        str(service.workers),
        "--runtime-threads",
        "1",
        "--log-level",
        "error",
        "--no-access-log",
    ]


def _taskiq_command(service: TaskiqWorkerService) -> list[str]:
    return [
        sys.executable,
        "-m",
        "taskiq",
        "worker",
        service.worker_module,
        "-w",
        str(service.workers),
    ]


def _log_paths(name: str) -> tuple[Path, Path]:
    STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return STACK_LOG_DIR / f"{name}.log", STACK_LOG_DIR / f"{name}.err"


def _tail_file(path: Path, lines: int = 40) -> str:
    if not path.exists():
        return "(нет файла)"
    content = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(content.splitlines()[-lines:]) or "(пусто)"


def _http_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.0) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _http_get_json(url: str, *, timeout_seconds: float) -> JsonValue:
    with urlopen(url, timeout=timeout_seconds) as response:
        status_code = int(response.status)
        if status_code < 200 or status_code >= 300:
            raise HTTPError(url, status_code, response.reason, response.headers, None)
        return require_json_value(json.loads(response.read().decode("utf-8")), field_name="response")


def _http_post_json(url: str, payload: JsonObject, *, timeout_seconds: float) -> JsonValue:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "test-stack-probe",
            "X-Trace-Id": "test-stack-probe-trace",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        status_code = int(response.status)
        if status_code < 200 or status_code >= 300:
            raise HTTPError(url, status_code, response.reason, response.headers, None)
        return require_json_value(json.loads(response.read().decode("utf-8")), field_name="response")


def _probe_capability_gateway_manifest() -> str | None:
    url = "http://127.0.0.1:9016/capability-gateway/api/v1/capabilities/manifest"
    try:
        payload = require_json_object(
            _http_get_json(url, timeout_seconds=10.0),
            field_name="capability_gateway_manifest",
        )
        if "version" not in payload:
            return f"capability_gateway manifest probe: unexpected payload {payload!r}"
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return f"capability_gateway manifest probe failed: {exc}"
    return None


def _probe_code_runner_python_execute() -> str | None:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="test_stack_probe_user",
        flow_id="test_stack_probe_flow",
        branch_id="main",
        session_id="test_stack_probe_flow:test_stack_probe_context",
        task_id="test_stack_probe_task",
        context_id="test_stack_probe_context",
        channel="a2a",
        request_id="test-stack-code-runner-probe",
        exp=execution_token_exp(300),
    )
    wall_time_limit_seconds = 30
    request = CodeExecutionRequest(
        kind="node",
        language="python",
        code='async def run(args, state):\n    return {"probe": "ok"}\n',
        entrypoint=None,
        wall_time_limit_seconds=wall_time_limit_seconds,
        sandbox=locked_down_code_sandbox_policy(
            wall_time_limit_seconds=wall_time_limit_seconds,
            cpu_time_limit_seconds=wall_time_limit_seconds,
            memory_limit_mb=256,
            filesystem_limit_mb=64,
            stdout_stderr_limit_bytes=1_048_576,
        ),
        args={},
        state={},
        context=CapabilityExecutionContext(
            execution_token=issue_execution_token(claims),
            company_id=claims.company_id,
            user_id=claims.user_id,
            flow_id=claims.flow_id,
            branch_id=claims.branch_id,
            session_id=claims.session_id,
            task_id=claims.task_id,
            context_id=claims.context_id,
            channel=claims.channel,
            request_id=claims.request_id,
            trace_id="test-stack-code-runner-probe-trace",
        ),
        capability_manifest=CapabilityManifest(version="test-stack-probe", capabilities=[]),
    )
    url = "http://127.0.0.1:9017/code-runner-python/api/v1/execute"
    try:
        payload = require_json_object(
            _http_post_json(url, request.model_dump(mode="json"), timeout_seconds=30.0),
            field_name="code_runner_execute_response",
        )
        if payload.get("status") != "completed":
            return f"code_runner_python execute probe failed: {payload!r}"
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return f"code_runner_python execute probe failed: {exc}"
    return None


def _run_sandbox_execute_probes() -> list[str]:
    errors: list[str] = []
    for attempt in range(3):
        if attempt > 0:
            time.sleep(1.0)
        errors = []
        for probe in (_probe_capability_gateway_manifest, _probe_code_runner_python_execute):
            failure = probe()
            if failure is not None:
                errors.append(failure)
        if not errors:
            return []
    return errors


def _redis_client(redis_url: str) -> redis.Redis:
    parsed = urlparse(redis_url)
    if parsed.hostname is None or parsed.port is None:
        raise ValueError(f"Некорректный Redis URL: {redis_url}")
    db_part = parsed.path.lstrip("/")
    return redis.Redis(
        host=parsed.hostname,
        port=parsed.port,
        db=int(db_part) if db_part else 0,
        decode_responses=True,
    )


def _taskiq_stream_ready(client: redis.Redis, stream_name: str) -> bool:
    """Consumer группы taskiq подключился к стриму — воркер реально слушает очередь."""
    if not client.exists(stream_name):
        return False
    try:
        groups_response = client.xinfo_groups(stream_name)
    except redis_exceptions.ResponseError:
        return False
    if not isinstance(groups_response, list):
        raise TypeError(f"XINFO GROUPS вернул не list: {type(groups_response)!r}")
    for group in groups_response:
        if not isinstance(group, dict):
            raise TypeError(f"XINFO GROUPS элемент не dict: {type(group)!r}")
        if str(group.get("name")) != _TASKIQ_CONSUMER_GROUP:
            continue
        consumers_raw = group.get("consumers")
        if consumers_raw is None:
            raise ValueError(f"XINFO GROUPS group {_TASKIQ_CONSUMER_GROUP!r} missing consumers")
        return int(consumers_raw) >= 1
    return False


@dataclass
class StackProcess:
    name: str
    kind: str
    pid: int
    port: int | None
    stream_name: str | None
    log_file: str
    err_file: str


def _spawn_granian(service: GranianService) -> tuple[subprocess.Popen[bytes], StackProcess]:
    log_path, err_path = _log_paths(service.name)
    log_handle = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")
    err_handle = open(err_path, "w", buffering=1, encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        _granian_command(service),
        stdout=log_handle,
        stderr=err_handle,
        env=_build_process_env(service.env),
        start_new_session=True,
    )
    return process, StackProcess(
        name=service.name,
        kind="granian",
        pid=process.pid,
        port=service.port,
        stream_name=None,
        log_file=str(log_path),
        err_file=str(err_path),
    )


def _spawn_taskiq(service: TaskiqWorkerService) -> tuple[subprocess.Popen[bytes], StackProcess]:
    log_path, err_path = _log_paths(service.name)
    log_handle = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")
    err_handle = open(err_path, "w", buffering=1, encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        _taskiq_command(service),
        stdout=log_handle,
        stderr=err_handle,
        env=_build_process_env(service.env),
        start_new_session=True,
    )
    return process, StackProcess(
        name=service.name,
        kind="taskiq",
        pid=process.pid,
        port=None,
        stream_name=service.stream_name,
        log_file=str(log_path),
        err_file=str(err_path),
    )


def _wait_granian_ready(
    service: GranianService, process: subprocess.Popen[bytes]
) -> str | None:
    """None если сервис готов, иначе текст ошибки."""
    url = f"http://127.0.0.1:{service.port}{service.readiness_path}"
    deadline = time.monotonic() + service.readiness_timeout
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            log_path, err_path = _log_paths(service.name)
            return (
                f"{service.name}: процесс завершился (exit_code={exit_code}) до readiness.\n"
                f"stderr tail:\n{_tail_file(err_path)}\n"
                f"stdout tail:\n{_tail_file(log_path)}"
            )
        if _http_ready(url):
            return None
        time.sleep(0.25)
    log_path, err_path = _log_paths(service.name)
    return (
        f"{service.name}: readiness {url} не прошёл за {service.readiness_timeout}s.\n"
        f"stderr tail:\n{_tail_file(err_path)}\n"
        f"stdout tail:\n{_tail_file(log_path)}"
    )


def _wait_taskiq_ready(
    service: TaskiqWorkerService, process: subprocess.Popen[bytes]
) -> str | None:
    client = _redis_client(_TASKIQ_REDIS_URL)
    deadline = time.monotonic() + service.readiness_timeout
    try:
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                log_path, err_path = _log_paths(service.name)
                return (
                    f"{service.name}: процесс завершился (exit_code={exit_code}) до readiness.\n"
                    f"stderr tail:\n{_tail_file(err_path)}\n"
                    f"stdout tail:\n{_tail_file(log_path)}"
                )
            if _taskiq_stream_ready(client, service.stream_name):
                return None
            time.sleep(0.25)
        log_path, err_path = _log_paths(service.name)
        return (
            f"{service.name}: consumer taskiq не появился в стриме {service.stream_name!r} "
            f"за {service.readiness_timeout}s.\n"
            f"stderr tail:\n{_tail_file(err_path)}\n"
            f"stdout tail:\n{_tail_file(log_path)}"
        )
    finally:
        client.close()


def _wait_external_ready(external: ExternalReadiness) -> str | None:
    deadline = time.monotonic() + external.readiness_timeout
    while time.monotonic() < deadline:
        if _http_ready(external.url):
            return None
        time.sleep(0.5)
    return f"{external.name}: readiness {external.url} не прошёл за {external.readiness_timeout}s (docker-compose)."


def _terminate_process_group(pid: int, *, graceful_timeout: float = 3.0) -> None:
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + graceful_timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass


def _write_manifest(
    processes: list[StackProcess],
    *,
    granian_services: tuple[GranianService, ...],
    taskiq_services: tuple[TaskiqWorkerService, ...],
) -> None:
    pytest_workers = resolve_pytest_workers()
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "controller_pid": os.getpid(),
        "pytest_workers_requested": pytest_workers,
        "stack_scale_factor": stack_scale_factor(pytest_workers),
        "stack_capacity": _stack_capacity_snapshot(granian_services, taskiq_services),
        "processes": [vars(stack_process) for stack_process in processes],
    }
    STACK_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_manifest_processes() -> list[StackProcess]:
    if not STACK_MANIFEST_PATH.exists():
        return []
    manifest = json.loads(STACK_MANIFEST_PATH.read_text(encoding="utf-8"))
    processes_raw = manifest.get("processes")
    if not isinstance(processes_raw, list):
        raise RuntimeError(f"Некорректный манифест стека: {STACK_MANIFEST_PATH}")
    return [StackProcess(**entry) for entry in processes_raw]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _port_listening(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def cmd_up() -> int:
    _bootstrap_parent_test_env()
    cmd_down(quiet=True)

    pytest_workers = resolve_pytest_workers()
    granian_services = build_granian_services(pytest_workers)
    taskiq_services = build_taskiq_worker_services(pytest_workers)
    started: list[tuple[str, subprocess.Popen[bytes]]] = []
    processes: list[StackProcess] = []

    for granian_service in granian_services:
        process, stack_process = _spawn_granian(granian_service)
        started.append((granian_service.name, process))
        processes.append(stack_process)
    for taskiq_service in taskiq_services:
        process, stack_process = _spawn_taskiq(taskiq_service)
        started.append((taskiq_service.name, process))
        processes.append(stack_process)

    process_by_name = dict(started)
    print(
        f"test_stack: WORKERS={pytest_workers} scale={stack_scale_factor(pytest_workers):.2f}; "
        f"запущено {len(granian_services)} granian + "
        f"{len(taskiq_services)} taskiq процессов, ожидание readiness..."
    )

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(processes) + len(EXTERNAL_READINESS)) as pool:
        futures = []
        for granian_service in granian_services:
            futures.append(
                pool.submit(
                    _wait_granian_ready, granian_service, process_by_name[granian_service.name]
                )
            )
        for taskiq_service in taskiq_services:
            futures.append(
                pool.submit(
                    _wait_taskiq_ready, taskiq_service, process_by_name[taskiq_service.name]
                )
            )
        for external in EXTERNAL_READINESS:
            futures.append(pool.submit(_wait_external_ready, external))
        for future in futures:
            failure = future.result()
            if failure is not None:
                errors.append(failure)

    if errors:
        print("test_stack: readiness FAILED, останавливаю стек:", file=sys.stderr)
        for error_text in errors:
            print(f"\n--- {error_text}", file=sys.stderr)
        for _, process in started:
            _terminate_process_group(process.pid)
        return 1

    probe_errors = _run_sandbox_execute_probes()
    if probe_errors:
        print("test_stack: sandbox execute probes FAILED, останавливаю стек:", file=sys.stderr)
        for error_text in probe_errors:
            print(f"\n--- {error_text}", file=sys.stderr)
        for _, process in started:
            _terminate_process_group(process.pid)
        return 1

    _write_manifest(
        processes,
        granian_services=granian_services,
        taskiq_services=taskiq_services,
    )
    print(f"test_stack: стек готов, манифест {STACK_MANIFEST_PATH}")
    return 0


def cmd_down(*, quiet: bool = False) -> int:
    processes = _read_manifest_processes()
    if not processes:
        if not quiet:
            print("test_stack: манифест отсутствует, останавливать нечего")
        STACK_MANIFEST_PATH.unlink(missing_ok=True)
        return 0
    for stack_process in processes:
        if _pid_alive(stack_process.pid):
            _terminate_process_group(stack_process.pid)
            if not quiet:
                print(f"test_stack: {stack_process.name} (pid={stack_process.pid}) остановлен")
    STACK_MANIFEST_PATH.unlink(missing_ok=True)
    if not quiet:
        print("test_stack: стек остановлен")
    return 0


def cmd_status() -> int:
    processes = _read_manifest_processes()
    if not processes:
        print("test_stack: стек не запущен (нет манифеста)")
        return 1
    all_ok = True
    client = _redis_client(_TASKIQ_REDIS_URL)
    try:
        for stack_process in processes:
            alive = _pid_alive(stack_process.pid)
            if stack_process.kind == "granian" and stack_process.port is not None:
                ready = alive and _http_ready(
                    f"http://127.0.0.1:{stack_process.port}/health"
                )
                detail = f"port={stack_process.port}"
            elif stack_process.kind == "taskiq" and stack_process.stream_name is not None:
                ready = alive and _taskiq_stream_ready(client, stack_process.stream_name)
                detail = f"stream={stack_process.stream_name}"
            else:
                ready = alive
                detail = ""
            status_text = "OK" if ready else "FAIL"
            all_ok = all_ok and ready
            print(
                f"  [{status_text}] {stack_process.name} "
                f"(kind={stack_process.kind}, pid={stack_process.pid}, {detail})"
            )
    finally:
        client.close()
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Супервизор тестового стека платформы")
    parser.add_argument("command", choices=("up", "down", "status"))
    args = parser.parse_args()
    if args.command == "up":
        return cmd_up()
    if args.command == "down":
        return cmd_down()
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
