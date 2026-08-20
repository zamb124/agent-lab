"""Live customer Postgres for datasource tests: not a platform DSN, not a mock."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings

CUSTOMER_DATABASE = "platform_datasource_customer"
CUSTOMER_HOST = "localhost"
CUSTOMER_PORT = 54322
CUSTOMER_USERNAME = "platform_user"
CUSTOMER_PASSWORD = "admin"
SEED_ITEM_ID = 1
SEED_ITEM_NAME = "alpha"

_MAKE_TEST_UP = (
    "Postgres probe database platform_datasource_customer is required for "
    "datasource tests. Start the stack with: make test-up"
)
_SCHEMA_RE = re.compile(r"^dsu[0-9a-f]+$")
_POSTGRES_TEST = "postgresql+asyncpg://platform_user:admin@localhost:54322"
_ADMIN_URL = f"{_POSTGRES_TEST}/platform_shared"
_CUSTOMER_URL = f"{_POSTGRES_TEST}/{CUSTOMER_DATABASE}"


@dataclass(frozen=True, slots=True)
class CustomerDatasource:
    datasource_id: str
    schema_name: str
    qualified_table: str
    query_by_id_sql: str
    insert_sql: str
    seed_id: int
    seed_name: str


def _sqlstate(exc: DBAPIError) -> str:
    orig = exc.orig
    if orig is None:
        raise ValueError("DBAPIError has no orig") from exc
    raw = orig.sqlstate
    if not isinstance(raw, str):
        raise TypeError(f"sqlstate must be str, got {type(raw).__name__}")
    return raw


async def ensure_customer_database() -> None:
    """CREATE DATABASE if missing. Existing docker volumes skip init.sql."""
    engine = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": CUSTOMER_DATABASE},
            )
            exists = result.scalar()
            if exists is not None:
                return
            try:
                await connection.execute(text(f"CREATE DATABASE {CUSTOMER_DATABASE}"))
            except DBAPIError as exc:
                if _sqlstate(exc) != "42P04":
                    raise
            await connection.execute(
                text(
                    f"GRANT ALL PRIVILEGES ON DATABASE {CUSTOMER_DATABASE} TO {CUSTOMER_USERNAME}"
                )
            )
    except OperationalError as exc:
        raise RuntimeError(_MAKE_TEST_UP) from exc
    except OSError as exc:
        raise RuntimeError(_MAKE_TEST_UP) from exc
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def platform_datasource_customer_db() -> None:
    await ensure_customer_database()


@pytest_asyncio.fixture
async def customer_datasource(
    platform_datasource_customer_db: None,
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> AsyncIterator[CustomerDatasource]:
    _ = platform_datasource_customer_db
    schema_name = f"dsu{unique_id}"
    if _SCHEMA_RE.fullmatch(schema_name) is None:
        raise ValueError(f"datasource test schema is not a safe identifier: {schema_name}")
    qualified_table = f"{schema_name}.items"
    engine = create_async_engine(_CUSTOMER_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            await connection.execute(
                text(
                    f"CREATE TABLE {qualified_table} "
                    "(id integer PRIMARY KEY, name text NOT NULL)"
                )
            )
            await connection.execute(
                text(f"INSERT INTO {qualified_table} (id, name) VALUES (:id, :name)"),
                {"id": SEED_ITEM_ID, "name": SEED_ITEM_NAME},
            )
    except OperationalError as exc:
        raise RuntimeError(_MAKE_TEST_UP) from exc
    except DBAPIError as exc:
        if _sqlstate(exc) == "3D000":
            raise RuntimeError(_MAKE_TEST_UP) from exc
        raise
    finally:
        await engine.dispose()

    created = await flows_client.post(
        "/flows/api/v1/datasources",
        headers=auth_headers_system,
        json={
            "connector_id": "postgres",
            "name": f"customer {unique_id}",
            "host": CUSTOMER_HOST,
            "port": CUSTOMER_PORT,
            "database_name": CUSTOMER_DATABASE,
            "username": CUSTOMER_USERNAME,
            "password": CUSTOMER_PASSWORD,
            "ssl_mode": "disable",
            "allowed_operations": ["select", "insert"],
        },
    )
    if created.status_code != 200:
        raise AssertionError(
            f"customer datasource create failed: {created.status_code} {created.text}"
        )
    payload = created.json()
    datasource_id = payload["datasource_id"]
    if not isinstance(datasource_id, str) or not datasource_id.strip():
        raise AssertionError("customer datasource create: datasource_id required")

    yield CustomerDatasource(
        datasource_id=datasource_id,
        schema_name=schema_name,
        qualified_table=qualified_table,
        query_by_id_sql=f"SELECT id, name FROM {qualified_table} WHERE id = :id",
        insert_sql=f"INSERT INTO {qualified_table} (id, name) VALUES (:id, :name)",
        seed_id=SEED_ITEM_ID,
        seed_name=SEED_ITEM_NAME,
    )

    deleted = await flows_client.delete(
        f"/flows/api/v1/datasources/{datasource_id}",
        headers=auth_headers_system,
    )
    if deleted.status_code not in {200, 204, 403, 404}:
        raise AssertionError(
            f"customer datasource teardown delete failed: {deleted.status_code} {deleted.text}"
        )
    drop_engine = create_async_engine(_CUSTOMER_URL)
    try:
        async with drop_engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema_name} CASCADE"))
    finally:
        await drop_engine.dispose()


def platform_shared_database_name() -> str:
    shared_url = get_settings().database.shared_url
    parsed = urlparse(shared_url)
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError(f"platform shared DSN has empty database name: {shared_url!r}")
    return database_name
