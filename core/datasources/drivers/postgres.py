"""Platform Postgres driver для DatasourceProtocol."""

from __future__ import annotations

from time import perf_counter

import asyncpg

from core.datasources.drivers.json_cells import json_row
from core.datasources.drivers.sql_endpoint import require_sql_endpoint
from core.datasources.models import (
    DatasourceColumn,
    DatasourceConnection,
    DatasourceExecuteResult,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceSslMode,
    DatasourceTable,
    DatasourceTestResult,
)
from core.datasources.sql_policy import bind_named_params
from core.types import JsonObject, JsonValue


class PostgresDatasourceDriver:
    async def test(self, connection: DatasourceConnection, password: str) -> DatasourceTestResult:
        started = perf_counter()
        conn = await self._connect(connection, password)
        try:
            version = await conn.fetchval("SELECT version()")
        finally:
            await conn.close()
        if not isinstance(version, str) or not version.strip():
            raise ValueError("postgres test: version() did not return text")
        latency_ms = int((perf_counter() - started) * 1000)
        return DatasourceTestResult(ok=True, latency_ms=latency_ms, server_version=version)

    async def introspect(
        self, connection: DatasourceConnection, password: str
    ) -> DatasourceSchemaSnapshot:
        conn = await self._connect(connection, password)
        try:
            rows = await conn.fetch(
                """
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
                """
            )
        finally:
            await conn.close()
        return _schema_from_information_schema(rows)

    async def query(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceQueryResult:
        rewritten, values = bind_named_params(sql, params)
        conn = await self._connect(connection, password)
        try:
            records = await conn.fetch(rewritten, *_asyncpg_args(values))
        finally:
            await conn.close()
        return _query_result(records, connection.max_rows)

    async def execute(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceExecuteResult:
        rewritten, values = bind_named_params(sql, params)
        conn = await self._connect(connection, password)
        try:
            status = await conn.execute(rewritten, *_asyncpg_args(values))
        finally:
            await conn.close()
        return DatasourceExecuteResult(rowcount=_rowcount_from_status(status))

    async def _connect(
        self, connection: DatasourceConnection, password: str
    ) -> asyncpg.Connection:
        host, port, database_name, username, ssl_mode = require_sql_endpoint(connection)
        timeout_s = connection.statement_timeout_ms / 1000
        return await asyncpg.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database_name,
            ssl=_ssl_arg(ssl_mode),
            timeout=10,
            command_timeout=timeout_s,
        )


def _ssl_arg(ssl_mode: DatasourceSslMode) -> str:
    match ssl_mode:
        case DatasourceSslMode.DISABLE:
            return "disable"
        case DatasourceSslMode.REQUIRE:
            return "require"
        case DatasourceSslMode.VERIFY_FULL:
            return "verify-full"


def _asyncpg_args(values: list[JsonValue]) -> list[object]:
    return [value for value in values]


def _rowcount_from_status(status: str) -> int:
    parts = status.split()
    if not parts:
        raise ValueError(f"postgres execute status empty: {status!r}")
    last = parts[-1]
    if not last.isdigit():
        raise ValueError(f"postgres execute status has no rowcount: {status!r}")
    return int(last)


def _query_result(records: list[asyncpg.Record], max_rows: int) -> DatasourceQueryResult:
    truncated = len(records) > max_rows
    sliced = records[:max_rows]
    columns = list(sliced[0].keys()) if sliced else []
    rows = [json_row(record, columns) for record in sliced]
    return DatasourceQueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    )


def _schema_from_information_schema(rows: list[asyncpg.Record]) -> DatasourceSchemaSnapshot:
    tables: dict[str, DatasourceTable] = {}
    order: list[str] = []
    for record in rows:
        schema_name = record["table_schema"]
        table_name = record["table_name"]
        column_name = record["column_name"]
        data_type = record["data_type"]
        if not isinstance(schema_name, str) or not isinstance(table_name, str):
            raise ValueError("information_schema row missing table identity")
        if not isinstance(column_name, str) or not isinstance(data_type, str):
            raise ValueError("information_schema row missing column identity")
        key = f"{schema_name}.{table_name}"
        table = tables.get(key)
        if table is None:
            table = DatasourceTable(table_name=key, columns=[])
            tables[key] = table
            order.append(key)
        table.columns.append(DatasourceColumn(name=column_name, data_type=data_type))
    return DatasourceSchemaSnapshot(tables=[tables[key] for key in order])
