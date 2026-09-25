"""
Идемпотентное создание сервисных БД и расширений по migrations/services.json.

Перед `scripts.db_migrate upgrade` вызывается автоматически: на старом томе Postgres
init.sql не перезапускается, поэтому новые БД (например platform_wiki) создаются здесь.
На каждую БД из postgres.databases ставится pg_stat_statements; vector — на БД из
postgres.vector_extensions (как migrations/postgres/init.sql).
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import parse_qs, unquote, urlparse

import asyncpg
from asyncpg.exceptions import InvalidPasswordError

from core.config import get_settings
from core.db.migration_manifest import load_migration_manifest
from core.logging import get_logger

logger = get_logger(__name__)
_PG_AUTH_HINT = (
    "Аутентификация PostgreSQL не удалась. Проверьте .env / DATABASE__* и conf.local.json (перекрывают conf.json). "
    "Пароль суперпользователя в Docker задаётся при первом создании тома; смена POSTGRES_PASSWORD в compose "
    "старый volume не обновляет — пересоздайте том или поправьте URL."
)
_SAFE_IDENT: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_CONNECT_TIMEOUT = 60.0
_COMMAND_TIMEOUT = 120.0


def _require_safe_ident(name: str, context: str) -> None:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"{context}: invalid PostgreSQL identifier: {name!r}")


def _connect_args(url: str) -> tuple[str, int, str, str, str, str]:
    prefix = "postgresql+asyncpg://"
    if url.startswith(prefix):
        normalized = "postgresql://" + url.removeprefix(prefix)
    elif url.startswith("postgresql://") or url.startswith("postgres://"):
        normalized = url
    else:
        raise ValueError("database.shared_url must be a postgresql URL")
    parsed = urlparse(normalized)
    host = parsed.hostname
    user = parsed.username
    password = parsed.password
    database = unquote(parsed.path.removeprefix("/"))
    if (
        host is None
        or host == ""
        or user is None
        or user == ""
        or password is None
        or database == ""
    ):
        raise ValueError("database.shared_url must include host, user, password and database")
    port = 5432 if parsed.port is None else parsed.port
    ssl_values = parse_qs(parsed.query).get("sslmode", [])
    if len(ssl_values) == 0:
        ssl = "disable"
    elif len(ssl_values) == 1 and ssl_values[0] in {"disable", "require"}:
        ssl = ssl_values[0]
    else:
        raise ValueError("database.shared_url sslmode must be disable or require")
    return host, port, unquote(user), unquote(password), database, ssl


def _pg_target_debug(url: str) -> str:
    host, port, user, password, database, _ssl = _connect_args(url)
    space_hint = ""
    if password != password.strip():
        space_hint = " Пароль в URL имеет пробелы по краям — уберите их."
    return (
        f"Цель подключения: {user}@{host}:{port}/{database}, "
        f"длина пароля в URL: {len(password)}.{space_hint}"
    )


async def _open(url: str, database: str) -> asyncpg.Connection:
    host, port, user, password, _database, ssl = _connect_args(url)
    try:
        return await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            ssl=ssl,
            timeout=_CONNECT_TIMEOUT,
            command_timeout=_COMMAND_TIMEOUT,
        )
    except InvalidPasswordError as exc:
        raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(url)}") from exc


async def open_postgres_connection(url: str) -> asyncpg.Connection:
    """Одно соединение к базе из URL. Пароль в ошибке не печатается."""
    target = _connect_args(url)
    return await _open(url, target[4])


async def _apply_extensions(
    connection: asyncpg.Connection,
    *,
    need_vector: bool,
) -> None:
    _ = await connection.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    if need_vector:
        _ = await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")


async def ensure_postgres_service_databases_async(
    *,
    reference_shared_url: str | None = None,
) -> None:
    """
    Подключение к служебной базе ``postgres``: имена из postgres.databases
    создаются, если их нет, затем GRANT; на каждой БД — pg_stat_statements;
    на БД из vector_extensions — extension vector.
    """
    postgres_config = load_migration_manifest().postgres
    databases = list(postgres_config.databases)
    vector_dbs = list(postgres_config.vector_extensions)

    if reference_shared_url is not None:
        shared_str = reference_shared_url.strip()
        if shared_str == "":
            raise ValueError("ensure_postgres_service_databases: reference_shared_url is empty")
    else:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if shared_url is None or shared_url.strip() == "":
            raise ValueError(
                "ensure_postgres_service_databases: set database.shared_url (DATABASE__SHARED_URL)"
            )
        shared_str = shared_url.strip()

    target = _connect_args(shared_str)
    role = target[2]
    shared_db_name = target[4]
    _require_safe_ident(role, "ensure_postgres_service_databases (роль из URL)")
    _require_safe_ident(shared_db_name, "ensure_postgres_service_databases (shared database)")
    for db_name in databases:
        _require_safe_ident(db_name, "ensure_postgres_service_databases (postgres.databases)")
    for ext_db in vector_dbs:
        if ext_db not in databases:
            raise ValueError(
                f"postgres.vector_extensions contains {ext_db!r} that is missing from postgres.databases"
            )
        _require_safe_ident(ext_db, "ensure_postgres_service_databases (vector_extensions)")

    admin = await _open(shared_str, "postgres")
    try:
        for db_name in databases:
            exists = await admin.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                db_name,
            )
            if exists is None:
                _ = await admin.execute(f"CREATE DATABASE {db_name}")
                logger.info("db.postgresql", db_name=db_name)
        for db_name in databases:
            _ = await admin.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {role}")
    except InvalidPasswordError as exc:
        raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(shared_str)}") from exc
    finally:
        await admin.close()

    for db_name in databases:
        connection = await _open(shared_str, db_name)
        try:
            await _apply_extensions(connection, need_vector=db_name in vector_dbs)
        except InvalidPasswordError as exc:
            raise RuntimeError(
                f"{_PG_AUTH_HINT}\nBase for extensions: {db_name}. {_pg_target_debug(shared_str)}"
            ) from exc
        finally:
            await connection.close()
