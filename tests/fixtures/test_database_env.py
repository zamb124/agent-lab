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
}
