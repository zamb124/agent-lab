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
  - TRUNCATE всех user-таблиц (кроме alembic_version) во всех 7 service-БД
  - `pg_terminate_backend` всех сторонних сессий перед TRUNCATE
  - `session_replication_role = replica` — отключает FK-триггеры, TRUNCATE <5s
  - TRUNCATE ... RESTART IDENTITY CASCADE одним запросом
  - FLUSHDB Redis DB 0/1 — убирает `mock_llm:*`, `session:*`, `taskiq:*` ключи

Защита от случайного запуска не на тестовом окружении: скрипт принимает
URL только с портом 54322 (Postgres test) и 63792 (Redis test). На любой
другой порт — `RuntimeError`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
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
_TEST_INFRA_EPOCH_FILE = Path("/tmp/platform_test_infra_epoch")
_TRUNCATE_ATTEMPTS = 5
_TRUNCATE_RETRY_SLEEP_SECONDS = 0.2
_TERMINATE_WAIT_SECONDS = 2.0


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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


async def _terminate_other_sessions(conn: asyncpg.Connection) -> int:
    """Закрывает все прочие подключения к текущей БД (кроме этого соединения).

    1. Терминируем ВСЕХ других.
    2. ЖДЁМ (до 30s), пока pg_locks не покажет 0 сторонних granted lock'ов.
    Возвращает суммарное число терминированных.
    """
    total = 0
    # Терминируем всех других.
    rows = await conn.fetch(
        """
        SELECT pid
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
        """
    )
    pids = [row["pid"] for row in rows]
    for pid in pids:
        terminated = await conn.fetchval(
            "SELECT pg_terminate_backend($1)", pid
        )
        if terminated:
            total += 1

    # Коротко ждём, пока сторонние lock'и исчезнут. Долгий rollback покрывает
    # retry/fallback ниже; здесь нельзя зависать на stale backend'е.
    if total:
        attempts = max(1, int(_TERMINATE_WAIT_SECONDS / 0.05))
        for _ in range(attempts):
            locks = await conn.fetch(
                """
                SELECT 1
                FROM pg_locks l
                LEFT JOIN pg_stat_activity a ON l.pid = a.pid
                WHERE l.pid <> pg_backend_pid()
                  AND l.granted = true
                  AND a.datname = current_database()
                LIMIT 1
                """
            )
            if not locks:
                break
            await asyncio.sleep(0.05)
    return total


async def _print_lock_diagnostics(conn: asyncpg.Connection, db_name: str) -> list[int]:
    """Печатает текущие lock'и чужих pid в этой БД и возвращает pid'ы блокеров."""
    print(f"  [{db_name}] TRUNCATE lock timeout — диагностика lock'ов:")
    locks = await conn.fetch(
        """
        SELECT l.locktype, l.mode, l.pid, c.relname, a.query
        FROM pg_locks l
        LEFT JOIN pg_class c ON l.relation = c.oid
        LEFT JOIN pg_stat_activity a ON l.pid = a.pid
        WHERE l.pid <> pg_backend_pid()
          AND l.granted = true
          AND a.datname = current_database()
        ORDER BY l.locktype, l.mode
        """
    )
    blocker_pids: set[int] = set()
    for row in locks:
        pid = row["pid"]
        if isinstance(pid, int):
            blocker_pids.add(pid)
        q = (row["query"] or "")[:60].replace("\n", " ")
        print(
            f"    {row['locktype']} {row['mode']} pid={pid} "
            f"rel={row['relname']} q={q!r}"
        )
    return sorted(blocker_pids)


async def _terminate_pids(conn: asyncpg.Connection, pids: list[int]) -> int:
    """Best-effort terminate для конкретных pid. Возвращает число успешно завершённых."""
    total = 0
    for pid in pids:
        terminated = await conn.fetchval("SELECT pg_terminate_backend($1)", pid)
        if terminated:
            total += 1
    return total


async def _truncate_with_retries(
    conn: asyncpg.Connection,
    *,
    db_name: str,
    quoted_tables: str,
) -> bool:
    """TRUNCATE с повторной зачисткой сессий на race с переподключившимися сервисами."""
    for attempt in range(1, _TRUNCATE_ATTEMPTS + 1):
        try:
            await conn.execute(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE")
            return True
        except (asyncpg.QueryCanceledError, asyncpg.LockNotAvailableError):
            blocker_pids = await _print_lock_diagnostics(conn, db_name)
            killed_blockers = await _terminate_pids(conn, blocker_pids)
            killed_sessions = await _terminate_other_sessions(conn)
            killed_total = killed_blockers + killed_sessions
            if killed_total:
                print(
                    f"  [{db_name}] TRUNCATE retry {attempt}/{_TRUNCATE_ATTEMPTS}: "
                    f"завершено блокирующих/сторонних сессий: {killed_total}"
                )
            if attempt >= _TRUNCATE_ATTEMPTS:
                return False
            await asyncio.sleep(_TRUNCATE_RETRY_SLEEP_SECONDS * attempt)
    return False


async def _delete_tables_fallback(
    conn: asyncpg.Connection,
    *,
    db_name: str,
    tables: list[str],
) -> None:
    """Fallback для stale AccessShareLock: DELETE совместим с обычным SELECT."""
    print(
        f"  [{db_name}] TRUNCATE заблокирован после {_TRUNCATE_ATTEMPTS} попыток; "
        "fallback DELETE + reset sequences"
    )
    await conn.execute("SET statement_timeout = '60s'")
    for table in tables:
        await conn.execute(f"DELETE FROM {_quote_ident(table)}")

    sequences = await conn.fetch(
        """
        SELECT sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
        """
    )
    for row in sequences:
        await conn.execute(f"ALTER SEQUENCE {_quote_ident(row['sequence_name'])} RESTART WITH 1")
    await conn.execute("SET statement_timeout = '5s'")


async def _truncate_database(base_dsn: str, db_name: str) -> int:
    """Truncate всех user-таблиц одной БД. Возвращает количество таблиц.

    Принцип: каждый TRUNCATE <5s (statement_timeout + lock_timeout = 5s).
    Для надёжности:
    1. Повторяем terminate сессий пока не убьём все.
    2. SET session_replication_role = replica — отключает FK-триггеры,
       TRUNCATE ... CASCADE выполняется без блокировок по FK.
    3. TRUNCATE по одной таблице — если падает, видим имя таблицы.
    """
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
        print(f"  [{db_name}] БД отсутствует, пропуск")
        return 0

    try:
        # Убиваем все сессии, которые держат relation lock'и.
        # Повторяем, пока не перестанут убиваться.
        total_killed = 0
        for _ in range(3):
            killed = await _terminate_other_sessions(conn)
            if killed:
                total_killed += killed
            else:
                break
        if total_killed:
            print(f"  [{db_name}] завершено сторонних сессий: {total_killed}")

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

        # `session_replication_role = replica` отключает FK enforcement.
        # TRUNCATE ... CASCADE не проверяет FK и не ждёт блокировок.
        await conn.execute("SET session_replication_role = replica")
        await conn.execute("SET statement_timeout = '5s'")
        await conn.execute("SET lock_timeout = '5s'")

        quoted = ", ".join(_quote_ident(name) for name in tables)
        truncated = await _truncate_with_retries(conn, db_name=db_name, quoted_tables=quoted)
        if not truncated:
            await _delete_tables_fallback(conn, db_name=db_name, tables=tables)
        mode = "TRUNCATE" if truncated else "DELETE fallback"
        print(f"  [{db_name}] {mode}: {len(tables)} таблиц")
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

    _TEST_INFRA_EPOCH_FILE.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
    print("db_test_reset: готово")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
