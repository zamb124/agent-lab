"""
Сброс тестовой БД (TRUNCATE managed-таблиц) и Redis (FLUSHDB) перед прогоном тестов.

Назначение: устранить накопленный мусор в `agentlab_postgres_test` и
`agentlab_redis_test` между прогонами тестов. Без этого:
  - dedup pgvector-поиск замедляется на накопленных vector_documents
    (см. `apps/crm/services/entity_service.py::_deduplicate_entities`)
  - 60-секундный polling task'ов (`tests/crm/knowledge_import_helpers.py`)
    не успевает дождаться завершения analyze, тесты падают по timeout
  - flaky-эффекты на test_02_entity_types / test_17_company_init из-за
    отсутствия ORDER BY и накопленного списка типов company `system`

Канон:
  - TRUNCATE с RESTART IDENTITY CASCADE для всех user-таблиц всех 7 service-БД,
    кроме `alembic_version` (миграции остаются актуальными)
  - FLUSHDB Redis DB 0 (state) и DB 1 (TaskIQ broker) — убивает застрявшие
    `mock_llm:*`, `session:*`, `*lock*`, `taskiq:*` ключи

Защита от случайного запуска не на тестовом окружении: скрипт принимает
URL только с портом 54322 (Postgres test) и 63792 (Redis test). На любой
другой порт — `RuntimeError`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import redis.asyncio as redis_asyncio


_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _REPO_ROOT / "migrations" / "services.json"

_TEST_POSTGRES_PORT = 54322
_TEST_REDIS_PORT = 63792
_TEST_POSTGRES_HOSTS = {"localhost", "127.0.0.1"}

# Defaults совпадают с tests/fixtures/test_database_env.py.
_DEFAULT_POSTGRES_DSN = "postgresql://platform_user:admin@localhost:54322"
_DEFAULT_REDIS_HOST = "localhost"


def _load_database_names() -> list[str]:
    """Список физических Postgres-БД из migrations/services.json."""
    with _MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    databases = manifest.get("postgres", {}).get("databases")
    if not isinstance(databases, list) or not databases:
        raise RuntimeError(
            f"migrations/services.json не содержит postgres.databases: {manifest}"
        )
    return list(databases)


def _assert_test_postgres(dsn: str) -> None:
    parsed = urlparse(dsn)
    if parsed.hostname not in _TEST_POSTGRES_HOSTS:
        raise RuntimeError(
            f"db_test_reset.py запрещено выполнять не на тестовом Postgres "
            f"(host {parsed.hostname!r}). Разрешены только {_TEST_POSTGRES_HOSTS}."
        )
    if parsed.port != _TEST_POSTGRES_PORT:
        raise RuntimeError(
            f"db_test_reset.py запрещено выполнять не на тестовом Postgres "
            f"(порт {parsed.port}). Тестовый порт — {_TEST_POSTGRES_PORT}."
        )


def _assert_test_redis(host: str, port: int) -> None:
    if host not in _TEST_POSTGRES_HOSTS:
        raise RuntimeError(
            f"db_test_reset.py запрещено выполнять не на тестовом Redis "
            f"(host {host!r}). Разрешены только {_TEST_POSTGRES_HOSTS}."
        )
    if port != _TEST_REDIS_PORT:
        raise RuntimeError(
            f"db_test_reset.py запрещено выполнять не на тестовом Redis "
            f"(порт {port}). Тестовый порт — {_TEST_REDIS_PORT}."
        )


async def _truncate_database(base_dsn: str, db_name: str) -> int:
    """Truncate всех user-таблиц одной БД. Возвращает количество таблиц."""
    parsed = urlparse(base_dsn)
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port

    try:
        conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=db_name,
        )
    except asyncpg.InvalidCatalogNameError:
        # БД ещё не создана (например, новый разработчик впервые запускает make test-up
        # до миграций) — пропускаем без шума.
        print(f"  [{db_name}] БД отсутствует, пропуск")
        return 0

    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name <> 'alembic_version'
            """
        )
        tables = [row["table_name"] for row in rows]
        if not tables:
            print(f"  [{db_name}] нет user-таблиц, пропуск")
            return 0

        # Один TRUNCATE — атомарно, FK не блокируют благодаря CASCADE.
        quoted = ", ".join(f'"{name}"' for name in tables)
        await conn.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
        print(f"  [{db_name}] TRUNCATE: {len(tables)} таблиц")
        return len(tables)
    finally:
        await conn.close()


async def _flush_redis(host: str, port: int, db: int) -> None:
    client = redis_asyncio.Redis(host=host, port=port, db=db)
    try:
        await client.flushdb()
        print(f"  [redis db={db}] FLUSHDB ok")
    finally:
        await client.aclose()


async def _main() -> int:
    base_dsn = _DEFAULT_POSTGRES_DSN
    _assert_test_postgres(base_dsn)

    redis_host = _DEFAULT_REDIS_HOST
    redis_port = _TEST_REDIS_PORT
    _assert_test_redis(redis_host, redis_port)

    print(f"Сброс тестовой БД: postgres={urlparse(base_dsn).hostname}:{urlparse(base_dsn).port}")
    databases = _load_database_names()
    total_tables = 0
    for db_name in databases:
        total_tables += await _truncate_database(base_dsn, db_name)
    print(f"Postgres: очищено {total_tables} таблиц в {len(databases)} БД")

    print(f"Сброс тестового Redis: {redis_host}:{redis_port}")
    for db in (0, 1):
        await _flush_redis(redis_host, redis_port, db)

    print("db_test_reset: готово")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
