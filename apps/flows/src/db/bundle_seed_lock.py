"""Один воркер flows сидирует каталог, остальные ждут тот же lock."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, unquote, urlparse

import asyncpg

from core.config import get_settings


@asynccontextmanager
async def flows_bundle_seed_lock() -> AsyncGenerator[None, None]:
    """Сессионный ``pg_advisory_lock`` на базе flows, пока идёт seed каталога."""
    url = get_settings().database.flows_url
    if url is None or url == "":
        raise ValueError("database.flows_url is not set")
    host, port, user, password, database, ssl = _connect_args(url)
    connection = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        ssl=ssl,
        timeout=10,
        command_timeout=300,
    )
    try:
        _ = await connection.execute(
            "SELECT pg_advisory_lock(hashtext($1))",
            "flows.bundle_seed",
        )
        yield
    finally:
        try:
            _ = await connection.execute(
                "SELECT pg_advisory_unlock(hashtext($1))",
                "flows.bundle_seed",
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
        raise ValueError("database.flows_url must be a postgresql URL")
    parsed = urlparse(normalized)
    host = parsed.hostname
    user = parsed.username
    password = parsed.password
    database = unquote(parsed.path.removeprefix("/"))
    if host is None or host == "" or user is None or user == "" or password is None or database == "":
        raise ValueError("database.flows_url must include host, user, password and database")
    port = 5432 if parsed.port is None else parsed.port
    ssl_values = parse_qs(parsed.query).get("sslmode", [])
    if len(ssl_values) == 0:
        ssl = "disable"
    elif len(ssl_values) == 1 and ssl_values[0] in {"disable", "require"}:
        ssl = ssl_values[0]
    else:
        raise ValueError("database.flows_url sslmode must be disable or require")
    return host, port, unquote(user), unquote(password), database, ssl
