"""
URL PostgreSQL для pytest и дочерних процессов (uvicorn, TaskIQ).

Должны совпадать с `migrations/postgres/init.sql` и `os.environ` в conftest.py:
отдельная БД на каждый каталог `migrations/<db>/`, иначе `oxyde_migrations` одной базы смешивается с другой.

Сервисы тест-окружения используют нестандартные порты чтобы не конфликтовать с dev:
  postgres  → 54322 (dev: 54321)
  redis     → 63792 (dev: 63791)
  redis-realtime → 63793 (dev: 8098)
  seaweedfs → 19002 (dev: 19001)
  livekit   → 7890  (dev: 7880)
  centrifugo → 19000 (dev: 8000)
  openfga   → 9093  (dev: 9090)
"""

import os
from pathlib import Path

_POSTGRES_TEST = "postgresql+asyncpg://platform_user:admin@localhost:54322"
_ROOT = Path(__file__).resolve().parents[2]
_OPENFGA_TEST_ENV_PATH = _ROOT / "reports" / "openfga-test.env"

# HS256 в PyJWT требует >=32 байт для platform auth / execution tokens.
TEST_HS256_JWT_SECRET = "platform-test-hs256-jwt-secret-32b!"
# LiveKit server (current image) rejects API secrets shorter than 32 characters.
TEST_LIVEKIT_API_SECRET = "platform-test-livekit-secret-32b!"
TEST_OFFICE_JWT_SECRET = "test-onlyoffice-jwt-secret"
if len(TEST_HS256_JWT_SECRET) < 32:
    raise ValueError("TEST_HS256_JWT_SECRET must be at least 32 bytes for HS256 tests")
if len(TEST_LIVEKIT_API_SECRET) < 32:
    raise ValueError("TEST_LIVEKIT_API_SECRET must be at least 32 characters for LiveKit")

# Subprocess (TaskIQ worker и т.д.) не наследует os.environ из conftest целиком: те же ключи,
# что выставляются в tests/conftest.py через setdefault, должны быть в TEST_DATABASE_ENV.
_TEST_SERVICE_ENV: dict[str, str] = {
    # Локальные сервисы тест-стека не должны идти через внешний HTTP_PROXY.
    "NO_PROXY": "localhost,127.0.0.1,::1",
    "no_proxy": "localhost,127.0.0.1,::1",
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "SERVER__FLOWS_SERVICE_URL": "http://localhost:9001",
    "SERVER__RAG_SERVICE_URL": "http://localhost:9002",
    "SERVER__CRM_SERVICE_URL": "http://localhost:9003",
    "SERVER__FRONTEND_SERVICE_URL": "http://localhost:9004",
    "SERVER__SYNC_SERVICE_URL": "http://localhost:9005",
    "SERVER__OFFICE_SERVICE_URL": "http://localhost:9008",
    "SERVER__VOICE_SERVICE_URL": "http://localhost:9015",
    "SERVER__CAPABILITY_GATEWAY_SERVICE_URL": "http://localhost:9016",
    "SERVER__CODE_RUNNER_PYTHON_SERVICE_URL": "http://localhost:9017",
    "SERVER__CODE_RUNNER_NODE_SERVICE_URL": "http://localhost:9018",
    "SERVER__CODE_RUNNER_GO_SERVICE_URL": "http://localhost:9019",
    "SERVER__CODE_RUNNER_CSHARP_SERVICE_URL": "http://localhost:9020",
    "SERVER__WORKTRACKER_SERVICE_URL": "http://localhost:9021",
    "SERVER__SECRETS_SERVICE_URL": "http://localhost:9022",
    "SERVER__SCHEDULER_SERVICE_URL": "http://localhost:9006",
    "SERVER__SEARCH_SERVICE_URL": "http://localhost:9010",
    "SERVER__WIKI_SERVICE_URL": "http://localhost:9023",
    "SERVER__GUEST_RUNTIME_SERVICE_URL": "http://localhost:9024",
    "SERVER__REALTIME_SERVICE_URL": "http://localhost:9025",
    "SERVER__STOCK_SERVICE_URL": "http://localhost:9026",
    "REALTIME__CENTRIFUGO_API_URL": "http://127.0.0.1:19000/api",
    "REALTIME__CENTRIFUGO_API_KEY": "platform-test-centrifugo-http-api-key",
    "CENTRIFUGO_WS_URL": "ws://127.0.0.1:19000/connection/websocket",
    "GUEST_RUNTIME__EXECUTOR": "inprocess",
    "GUEST_RUNTIME__MAX_LEASES_PER_COMPANY": "32",
    "GUEST_RUNTIME__MAX_LEASES_CLUSTER": "128",
    "DATABASE__SEARCH_URL": f"{_POSTGRES_TEST}/platform_search",
    "DATABASE__SECRETS_URL": f"{_POSTGRES_TEST}/platform_secrets",
    "SECRETS__ENCRYPTION_KEY": "test-secrets-encryption-key-fixed",
    "S3__ENABLED": "true",
    "S3__ENDPOINT_URL": "http://localhost:19002",
    "S3__BUCKET_NAME": "test-bucket",
    "S3__ACCESS_KEY_ID": "s3admin",
    "S3__SECRET_ACCESS_KEY": "s3admin",
    "S3__REGION_NAME": "us-east-1",
    "S3__PROVIDER": "seaweedfs",
    "S3__PATH_STYLE": "true",
    "LLM__PROVIDER": "openrouter",
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    # См. tests/conftest.py: тестовый pgvector использует deterministic embeddings;
    # provider_litserve остаётся каноничным embedding provider без внешнего API key.
    "RAG__EMBEDDING__PROVIDER": "provider_litserve",
    "RAG__EMBEDDING__API__MODEL": "qwen/qwen3-embedding-0.6b",
    "RAG__EMBEDDING__API__DIMENSION": "1024",
    "RAG__EMBEDDING__API__MRL_OUTPUT_DIMENSION": "1024",
    "RAG__DOCUMENT_INDEXING__SEARCH_DEFAULTS__RERANKER__ENABLED": "true",
    "VOICE__STT__PROVIDER": "mock",
    "VOICE__STT__MOCK_TRANSCRIPT_TEXT": "Тестовая транскрипция sync worker",
}


def ensure_local_no_proxy() -> None:
    """Добавляет localhost/127.0.0.1/::1 в NO_PROXY текущего процесса.

    urllib (readiness-пробы) и httpx (клиенты фикстур) честно ходят через
    HTTP(S)_PROXY шелла: без bypass локальные адреса уезжают на внешний прокси,
    который не видит localhost пользователя. Внешний egress при этом продолжает
    идти через прокси — NO_PROXY только расширяет список обхода.
    """
    for key in ("NO_PROXY", "no_proxy"):
        bypass = [part.strip() for part in os.environ.get(key, "").split(",") if part.strip()]
        for host in ("localhost", "127.0.0.1", "::1"):
            if host not in bypass:
                bypass.append(host)
        os.environ[key] = ",".join(bypass)


def load_openfga_test_env_overlay() -> dict[str, str]:
    """reports/openfga-test.env после `make test-up` (store/model ids). Без файла — OpenFGA off."""
    if not _OPENFGA_TEST_ENV_PATH.is_file():
        return {}
    overlay: dict[str, str] = {}
    for line in _OPENFGA_TEST_ENV_PATH.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if key.startswith("OPENFGA__"):
            overlay[key] = value
    return overlay


TEST_DATABASE_ENV: dict[str, str] = {
    "SERVER__PLATFORM_PUBLIC_BASE_URL": "http://system.lvh.me:9004",
    "DATABASE__POOL_MAX_CONNECTIONS": "2",
    "DATABASE__SHARED_URL": f"{_POSTGRES_TEST}/platform_shared",
    "DATABASE__FLOWS_URL": f"{_POSTGRES_TEST}/platform_agents",
    "DATABASE__CRM_URL": f"{_POSTGRES_TEST}/platform_crm",
    "DATABASE__SYNC_URL": f"{_POSTGRES_TEST}/platform_sync",
    "DATABASE__RAG_URL": f"{_POSTGRES_TEST}/platform_rag",
    "DATABASE__OFFICE_URL": f"{_POSTGRES_TEST}/platform_office",
    "DATABASE__WORKTRACKER_URL": f"{_POSTGRES_TEST}/platform_worktracker",
    "DATABASE__SECRETS_URL": f"{_POSTGRES_TEST}/platform_secrets",
    "DATABASE__TRACING_URL": f"{_POSTGRES_TEST}/platform_tracing",
    "DATABASE__WIKI_URL": f"{_POSTGRES_TEST}/platform_wiki",
    "DATABASE__REALTIME_URL": f"{_POSTGRES_TEST}/platform_realtime",
    "DATABASE__STOCK_URL": f"{_POSTGRES_TEST}/platform_stock",
    "DATABASE__REDIS_URL": "redis://localhost:63792/0",
    "TASKS__BROKER_URL": "redis://localhost:63792/1",
    "AUTH__JWT_SECRET_KEY": TEST_HS256_JWT_SECRET,
    "OFFICE__JWT_SECRET": TEST_OFFICE_JWT_SECRET,
    "CALLS__LIVEKIT_URL": "ws://localhost:7890",
    "CALLS__LIVEKIT_API_KEY": "devkey",
    "CALLS__LIVEKIT_API_SECRET": TEST_LIVEKIT_API_SECRET,
    # Без overlay store/model: enabled=false. После bootstrap — overlay включает OpenFGA.
    "OPENFGA__API_URL": "http://127.0.0.1:9093",
    "OPENFGA__ENABLED": "false",
    **_TEST_SERVICE_ENV,
    **load_openfga_test_env_overlay(),
}
