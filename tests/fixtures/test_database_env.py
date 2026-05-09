"""
URL PostgreSQL для pytest и дочерних процессов (uvicorn, TaskIQ).

Должны совпадать с `migrations/postgres/init.sql` и `os.environ` в conftest.py:
отдельная БД на каждое Alembic-дерево, иначе `alembic_version` одной миграции ломает другую.

Сервисы тест-окружения используют нестандартные порты чтобы не конфликтовать с dev:
  postgres  → 54322 (dev: 54321)
  redis     → 63792 (dev: 63791)
  minio     → 19002 (dev: 19001)
  livekit   → 7890  (dev: 7880)
"""

_POSTGRES_TEST = "postgresql+asyncpg://platform_user:admin@localhost:54322"

# Subprocess (TaskIQ worker и т.д.) не наследует os.environ из conftest целиком: те же ключи,
# что выставляются в tests/conftest.py через setdefault, должны быть в TEST_DATABASE_ENV.
_TEST_SERVICE_ENV: dict[str, str] = {
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "SERVER__FLOWS_SERVICE_URL": "http://localhost:9001",
    "SERVER__RAG_SERVICE_URL": "http://localhost:9002",
    "SERVER__CRM_SERVICE_URL": "http://localhost:9003",
    "SERVER__FRONTEND_SERVICE_URL": "http://localhost:9004",
    "SERVER__SYNC_SERVICE_URL": "http://localhost:9005",
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
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    # См. tests/conftest.py: OpenRouter + Qwen model id без локального LitServe в subprocess.
    "RAG__EMBEDDING__PROVIDER": "openrouter",
    "RAG__EMBEDDING__MODEL": "qwen/qwen3-embedding-4b",
    "RAG__EMBEDDING__DIMENSION": "1024",
    "RAG__EMBEDDING__MRL_OUTPUT_DIMENSION": "1024",
    "RAG__DOCUMENT_INDEXING__SEARCH_DEFAULTS__RERANKER__ENABLED": "false",
    "VOICE__STT__PROVIDER": "mock",
    "VOICE__STT__MOCK_TRANSCRIPT_TEXT": "Тестовая транскрипция sync worker",
}

TEST_DATABASE_ENV: dict[str, str] = {
    "SERVER__PLATFORM_PUBLIC_BASE_URL": "http://testserver",
    "DATABASE__SHARED_URL": f"{_POSTGRES_TEST}/platform_shared",
    "DATABASE__FLOWS_URL": f"{_POSTGRES_TEST}/platform_agents",
    "DATABASE__CRM_URL": f"{_POSTGRES_TEST}/platform_crm",
    "DATABASE__SYNC_URL": f"{_POSTGRES_TEST}/platform_sync",
    "DATABASE__RAG_URL": f"{_POSTGRES_TEST}/platform_rag",
    "DATABASE__OFFICE_URL": f"{_POSTGRES_TEST}/platform_office",
    "DATABASE__TRACING_URL": f"{_POSTGRES_TEST}/platform_tracing",
    "DATABASE__REDIS_URL": "redis://localhost:63792/0",
    "TASKS__BROKER_URL": "redis://localhost:63792/1",
    "CALLS__LIVEKIT_URL": "ws://localhost:7890",
    "CALLS__LIVEKIT_API_KEY": "devkey",
    "CALLS__LIVEKIT_API_SECRET": "secret",
    **_TEST_SERVICE_ENV,
}
