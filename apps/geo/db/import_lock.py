"""Сессионный ``pg_try_advisory_lock`` OSM-импорта на отдельном соединении.

Один импортер на кластер: конкурентные тики (cron, bootstrap, ручной
enqueue) сериализуются — второй получает ``False`` и завершается skip.
Канон — ``apps/crm/db/company_init_lock.py``: lock держит своё соединение,
пока импорт коммитит короткие транзакции на пуле.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, unquote, urlparse

import asyncpg

_LOCK_KEY = "geo.osm_import"


@asynccontextmanager
async def geo_import_lock(geo_url: str | None) -> AsyncGenerator[bool, None]:
    """``True`` — lock взят; ``False`` — импорт уже идёт в другом процессе."""
    if geo_url is None or geo_url == "":
        raise ValueError("database.geo_url is not set")
    host, port, user, password, database, ssl = _connect_args(geo_url)
    connection = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        ssl=ssl,
        timeout=10,
        command_timeout=30,
    )
    try:
        acquired = bool(
            await connection.fetchval(
                "SELECT pg_try_advisory_lock(hashtext($1))", _LOCK_KEY
            )
        )
        try:
            yield acquired
        finally:
            if acquired:
                _ = await connection.execute(
                    "SELECT pg_advisory_unlock(hashtext($1))", _LOCK_KEY
                )
    finally:
        await connection.close()


def _connect_args(url: str) -> tuple[str, int, str, str, str, str]:
    prefix = "postgresql+asyncpg://"
    if url.startswith(prefix):
        normalized = "postgresql://" + url.removeprefix(prefix)
    elif url.startswith("postgresql://") or url.startswith("postgres://"):
        normalized = url
    else:
        raise ValueError("database.geo_url must be a postgresql URL")
    parsed = urlparse(normalized)
    host = parsed.hostname
    user = parsed.username
    password = parsed.password
    database = unquote(parsed.path.removeprefix("/"))
    if host is None or host == "" or user is None or user == "" or password is None or database == "":
        raise ValueError("database.geo_url must include host, user, password and database")
    port = 5432 if parsed.port is None else parsed.port
    ssl_values = parse_qs(parsed.query).get("sslmode", [])
    if len(ssl_values) == 0:
        ssl = "disable"
    elif len(ssl_values) == 1 and ssl_values[0] in {"disable", "require"}:
        ssl = ssl_values[0]
    else:
        raise ValueError("database.geo_url sslmode must be disable or require")
    return host, port, unquote(user), unquote(password), database, ssl
