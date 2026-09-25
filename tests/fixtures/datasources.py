"""Live customer Postgres for datasource tests: not a platform DSN, not a mock."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse

import asyncpg
import pytest_asyncio
from asyncpg.exceptions import (
    DuplicateDatabaseError,
    InvalidCatalogNameError,
    PostgresConnectionError,
)
from httpx import AsyncClient

from core.config import get_settings
from core.types import parse_json_object

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
_CONNECT_TIMEOUT = 30.0
_COMMAND_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class CustomerDatasource:
    datasource_id: str
    schema_name: str
    qualified_table: str
    query_by_id_sql: str
    insert_sql: str
    seed_id: int
    seed_name: str


async def _connect(database: str) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(
            host=CUSTOMER_HOST,
            port=CUSTOMER_PORT,
            user=CUSTOMER_USERNAME,
            password=CUSTOMER_PASSWORD,
            database=database,
            ssl="disable",
            timeout=_CONNECT_TIMEOUT,
            command_timeout=_COMMAND_TIMEOUT,
        )
    except (OSError, PostgresConnectionError, InvalidCatalogNameError) as exc:
        raise RuntimeError(_MAKE_TEST_UP) from exc


async def ensure_customer_database() -> None:
    """CREATE DATABASE if missing. Existing docker volumes skip init.sql."""
    connection = await _connect("platform_shared")
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            CUSTOMER_DATABASE,
        )
        if exists is None:
            try:
                _ = await connection.execute(f"CREATE DATABASE {CUSTOMER_DATABASE}")
            except DuplicateDatabaseError as exc:
                _ = exc
        _ = await connection.execute(
            f"GRANT ALL PRIVILEGES ON DATABASE {CUSTOMER_DATABASE} TO {CUSTOMER_USERNAME}"
        )
    finally:
        await connection.close()


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
    connection = await _connect(CUSTOMER_DATABASE)
    try:
        _ = await connection.execute(f"CREATE SCHEMA {schema_name}")
        _ = await connection.execute(
            f"CREATE TABLE {qualified_table} (id integer PRIMARY KEY, name text NOT NULL)"
        )
        _ = await connection.execute(
            f"INSERT INTO {qualified_table} (id, name) VALUES ($1, $2)",
            SEED_ITEM_ID,
            SEED_ITEM_NAME,
        )
    finally:
        await connection.close()

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
    parsed = parse_json_object(created.text, "datasource create")
    datasource_id = parsed["datasource_id"]
    if not isinstance(datasource_id, str) or datasource_id.strip() == "":
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
    drop_connection = await _connect(CUSTOMER_DATABASE)
    try:
        _ = await drop_connection.execute(f"DROP SCHEMA {schema_name} CASCADE")
    finally:
        await drop_connection.close()


def platform_shared_database_name() -> str:
    shared_url = get_settings().database.shared_url
    if shared_url is None or shared_url == "":
        raise ValueError("database.shared_url is not set")
    parsed = urlparse(shared_url)
    database_name = parsed.path.lstrip("/")
    if database_name == "":
        raise ValueError(f"platform shared DSN has empty database name: {shared_url!r}")
    return database_name
