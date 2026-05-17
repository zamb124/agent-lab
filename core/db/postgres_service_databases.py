"""
Идемпотентное создание сервисных БД и расширений pgvector по migrations/services.json.

Не вызывается из scripts.db_migrate: миграции Alembic идут сразу к целевым URL. Для ручного/скриптового
вызова (идемпотентное создание сервисных БД и расширения vector) —
asyncio.run(ensure_postgres_service_databases_async()).
"""

from __future__ import annotations

import re
from typing import Final

from asyncpg.exceptions import InvalidPasswordError
from sqlalchemy import pool, text
from sqlalchemy.engine.url import make_url
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

def _pg_target_debug(shared_url: str) -> str:
    u = make_url(shared_url)
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
    postgres.databases, при отсутствии — CREATE DATABASE и GRANT; на БД из vector_extensions — extension vector.
    Раньше использовалась отдельная БД postgres; на части pg_hba / кастомных кластеров к ней иначе пускают,
    из‑за чего миграции ломались при том же URL, с которым shared уже подключался.

    Args:
        reference_shared_url: если задан (например в pytest), подставляется вместо get_settings().database.shared_url.
    """
    manifest = load_migration_manifest()
    postgres_cfg = manifest.get("postgres")
    if not postgres_cfg:
        return

    databases: list[str] = list(postgres_cfg["databases"])
    vector_dbs: list[str] = list(postgres_cfg.get("vector_extensions", []))

    if reference_shared_url is not None and str(reference_shared_url).strip():
        shared_str = str(reference_shared_url).strip()
    else:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if not shared_url or not str(shared_url).strip():
            raise ValueError(
                "ensure_postgres_service_databases: задайте database.shared_url (DATABASE__SHARED_URL)"
            )
        shared_str = str(shared_url)

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
    try:
        async with admin_engine.connect() as conn:
            for db_name in databases:
                chk = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                )
                if chk.first() is None:
                    await conn.execute(text(f"CREATE DATABASE {db_name}"))
                    logger.info("Создана отсутствующая БД PostgreSQL: %s", db_name)

            for db_name in databases:
                await conn.execute(text(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {role}"))

            if shared_db_name in vector_dbs:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except InvalidPasswordError as e:
        raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(shared_str)}") from e
    except OperationalError as e:
        if isinstance(getattr(e, "orig", None), InvalidPasswordError):
            raise RuntimeError(f"{_PG_AUTH_HINT}\n{_pg_target_debug(shared_str)}") from e
        raise
    finally:
        await admin_engine.dispose()

    for ext_db in vector_dbs:
        if ext_db == shared_db_name:
            continue
        db_url = str(make_url(shared_str).set(database=ext_db))
        v_engine = create_async_engine(db_url, poolclass=pool.NullPool)
        try:
            async with v_engine.begin() as v_conn:
                await v_conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except InvalidPasswordError as e:
            raise RuntimeError(
                f"{_PG_AUTH_HINT}\nБаза для vector: {ext_db}. {_pg_target_debug(db_url)}"
            ) from e
        except OperationalError as e:
            if isinstance(getattr(e, "orig", None), InvalidPasswordError):
                raise RuntimeError(
                    f"{_PG_AUTH_HINT}\nБаза для vector: {ext_db}. {_pg_target_debug(db_url)}"
                ) from e
            raise
        finally:
            await v_engine.dispose()
