"""
URL PostgreSQL для pytest и дочерних процессов (uvicorn, TaskIQ).

Должны совпадать с `migrations/postgres/init.sql` и `os.environ` в conftest.py:
отдельная БД на каждое Alembic-дерево, иначе `alembic_version` одной миграции ломает другую.
"""

_POSTGRES_TEST = "postgresql+asyncpg://platform_user:admin@localhost:54322"

TEST_DATABASE_ENV: dict[str, str] = {
    "DATABASE__SHARED_URL": f"{_POSTGRES_TEST}/platform_shared",
    "DATABASE__AGENTS_URL": f"{_POSTGRES_TEST}/platform_agents",
    "DATABASE__CRM_URL": f"{_POSTGRES_TEST}/platform_crm",
    "DATABASE__SYNC_URL": f"{_POSTGRES_TEST}/platform_sync",
    "DATABASE__RAG_URL": f"{_POSTGRES_TEST}/platform_rag",
}
