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

from asyncpg.exceptions import InvalidPasswordError
from sqlalchemy import pool, text
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings
from core.db.migration_manifest import load_migration_manifest
from core.logging import get_logger

logger = get_logger(__name__)
_PG_AUTH_HINT = (
    "Аутентификация PostgreSQL не удалась. Проверьте .env / DATABASE__* и conf.local.json (перекрывают conf.json). "
    "Пароль суперпользователя в Docker задаётся при первом создании тома; смена POSTGRES_PASSWORD в compose "
    "старый volume не обновляет — пересоздайте том или поправьте URL."
)

def _pg_target_debug(database_url: str | URL) -> str:
    # str(URL) в SQLAlchemy маскирует пароль как "***" — для диагностики нужен объект URL или исходная строка.
    u = database_url if isinstance(database_url, URL) else make_url(database_url)
    host = u.host or "?"
    port = u.port or "?"
    user = u.username or "?"
    db = u.database or "?"
    raw_pw = u.password
    pw_len = len(raw_pw) if raw_pw else 0
    space_hint = ""
    if raw_pw is not None and raw_pw != raw_pw.strip():
        space_hint = " Пароль в URL имеет пробелы по краям — уберите их."
    return f"Цель подключения: {user}@{host}:{port}/{db}, длина пароля в URL: {pw_len}.{space_hint}"

_SAFE_IDENT: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _require_safe_ident(name: str, context: str) -> None:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"{context}: недопустимый идентификатор PostgreSQL: {name!r}")

async def ensure_postgres_service_databases_async(
    *,
    reference_shared_url: str | None = None,
) -> None:
    """
    Подключение к той же БД, что в shared_url (как Alembic для shared): на кластере проверяются имена из
    postgres.databases, при отсутствии — CREATE DATABASE и GRANT; на каждой БД — pg_stat_statements;
    на БД из vector_extensions — extension vector.
    Раньше использовалась отдельная БД postgres; на части pg_hba / кастомных кластеров к ней иначе пускают,
    из‑за чего миграции ломались при том же URL, с которым shared уже подключался.

    Аргументы:
        reference_shared_url: если задан (например в pytest), подставляется вместо get_settings().database.shared_url.
    """
    postgres_config = load_migration_manifest().postgres
    databases = list(postgres_config.databases)
    vector_dbs = list(postgres_config.vector_extensions)

    if reference_shared_url is not None:
        shared_str = reference_shared_url.strip()
        if not shared_str:
            raise ValueError("ensure_postgres_service_databases: reference_shared_url пуст")
    else:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if not shared_url or not shared_url.strip():
            raise ValueError(
                "ensure_postgres_service_databases: задайте database.shared_url (DATABASE__SHARED_URL)"
            )
        shared_str = shared_url.strip()

    base = make_url(shared_str)
    shared_db_name = base.database
    if not shared_db_name:
        raise ValueError("ensure_postgres_service_databases: в database.shared_url не указано имя базы (путь после /)")

    role = base.username
    if not role:
        raise ValueError("ensure_postgres_service_databases: в database.shared_url нет имени пользователя")

    _require_safe_ident(role, "ensure_postgres_service_databases (роль из URL)")
    for db_name in databases:
        _require_safe_ident(db_name, "ensure_postgres_service_databases (postgres.databases)")

    for ext_db in vector_dbs:
        if ext_db not in databases:
            raise ValueError(
                f"postgres.vector_extensions содержит {ext_db!r}, которого нет в postgres.databases"
            )
        _require_safe_ident(ext_db, "ensure_postgres_service_databases (vector_extensions)")

    admin_engine = create_async_engine(
        shared_str,
        poolclass=pool.NullPool,
        isolation_level="AUTOCOMMIT",
    )
    created_databases: list[str] = []
    try:
        async with admin_engine.connect() as conn:
            for db_name in databases:
                chk = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                )
                if chk.first() is None:
                    _ = await conn.execute(text(f"CREATE DATABASE {db_name}"))
                    created_databases.append(db_name)
                    logger.info("Создана отсутствующая БД PostgreSQL: %s", db_name)

            for db_name in databases:
                _ = await conn.execute(
                    text(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {role}")
                )

            _ = await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
            if shared_db_name in vector_dbs:
                _ = await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except InvalidPasswordError as e:
        raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(shared_str)}") from e
    except OperationalError as e:
        if isinstance(e.orig, InvalidPasswordError):
            raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(shared_str)}") from e
        raise
    finally:
        await admin_engine.dispose()

    for db_name in databases:
        if db_name == shared_db_name:
            continue
        need_vector = db_name in vector_dbs
        # Не str(URL): SQLAlchemy маскирует пароль "***" и ломает auth.
        db_url = make_url(shared_str).set(database=db_name)
        db_engine = create_async_engine(db_url, poolclass=pool.NullPool)
        try:
            async with db_engine.begin() as db_conn:
                _ = await db_conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
                if need_vector:
                    _ = await db_conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except InvalidPasswordError as e:
            raise RuntimeError(
                f"{_PG_AUTH_HINT}\nБаза для extensions: {db_name}. {_pg_target_debug(db_url)}"
            ) from e
        except OperationalError as e:
            if isinstance(e.orig, InvalidPasswordError):
                raise RuntimeError(
                    f"{_PG_AUTH_HINT}\nБаза для extensions: {db_name}. {_pg_target_debug(db_url)}"
                ) from e
            raise
        finally:
            await db_engine.dispose()
