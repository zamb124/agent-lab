"""Platform ClickHouse driver для DatasourceProtocol."""

from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver.summary import QuerySummary

from core.datasources.drivers.json_cells import json_row
from core.datasources.drivers.sql_endpoint import (
    require_sql_endpoint,
    statement_timeout_connect_seconds,
)
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
from core.datasources.sql_policy import bind_named_params, rewrite_placeholders_pyformat
from core.types import JsonObject, JsonValue, require_json_value


class ClickHouseDatasourceDriver:
    async def test(self, connection: DatasourceConnection, password: str) -> DatasourceTestResult:
        started = perf_counter()
        client = await self._connect(connection, password)
        try:
            result = await client.query("SELECT version()")
        finally:
            await client.close()
        version = _first_cell_text(
            [
                [require_json_value(cell, "clickhouse version()") for cell in row]
                for row in result.result_rows
            ],
            "clickhouse version()",
        )
        latency_ms = int((perf_counter() - started) * 1000)
        return DatasourceTestResult(ok=True, latency_ms=latency_ms, server_version=version)

    async def introspect(
        self, connection: DatasourceConnection, password: str
    ) -> DatasourceSchemaSnapshot:
        client = await self._connect(connection, password)
        try:
            result = await client.query(
                """
                SELECT database, table, name, type
                FROM system.columns
                WHERE database = currentDatabase()
                ORDER BY table, position
                """
            )
        finally:
            await client.close()
        return _schema_from_rows(
            [
                [require_json_value(cell, "clickhouse system.columns") for cell in row]
                for row in result.result_rows
            ]
        )

    async def query(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceQueryResult:
        _rewritten, _values = bind_named_params(sql, params)
        pyformat_sql = rewrite_placeholders_pyformat(sql)
        client = await self._connect(connection, password)
        try:
            result = await client.query(pyformat_sql, parameters=_clickhouse_params(params))
        finally:
            await client.close()
        columns = list(result.column_names)
        records = result.result_rows
        truncated = len(records) > connection.max_rows
        sliced = records[: connection.max_rows]
        rows = [
            json_row(
                {column: record[index] for index, column in enumerate(columns)},
                columns,
            )
            for record in sliced
        ]
        return DatasourceQueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
        )

    async def execute(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceExecuteResult:
        _rewritten, _values = bind_named_params(sql, params)
        pyformat_sql = rewrite_placeholders_pyformat(sql)
        client = await self._connect(connection, password)
        try:
            result = await client.command(pyformat_sql, parameters=_clickhouse_params(params))
        finally:
            await client.close()
        return DatasourceExecuteResult(rowcount=_command_rowcount(result))

    async def _connect(self, connection: DatasourceConnection, password: str) -> AsyncClient:
        host, port, database_name, username, ssl_mode = require_sql_endpoint(connection)
        timeout_s = statement_timeout_connect_seconds(connection.statement_timeout_ms)
        return await clickhouse_connect.get_async_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database_name,
            secure=_clickhouse_secure(ssl_mode),
            verify=ssl_mode == DatasourceSslMode.VERIFY_FULL,
            connect_timeout=timeout_s,
            send_receive_timeout=timeout_s,
        )


def _clickhouse_secure(ssl_mode: DatasourceSslMode) -> bool:
    return ssl_mode != DatasourceSslMode.DISABLE


def _clickhouse_params(params: JsonObject) -> dict[str, JsonValue]:
    return dict(params)


def _first_cell_text(rows: Sequence[Sequence[JsonValue]], label: str) -> str:
    if not rows or not rows[0]:
        raise ValueError(f"{label}: empty result")
    value = rows[0][0]
    if value is None:
        raise ValueError(f"{label}: null")
    text = str(value)
    if not text.strip():
        raise ValueError(f"{label}: empty text")
    return text


def _command_rowcount(result: str | int | Sequence[str] | QuerySummary) -> int:
    if isinstance(result, int):
        if result < 0:
            raise ValueError(f"clickhouse command rowcount invalid: {result}")
        return result
    if isinstance(result, str):
        if not result.isdigit():
            raise ValueError(f"clickhouse command status has no rowcount: {result!r}")
        return int(result)
    if isinstance(result, QuerySummary):
        written = result.summary.get("written_rows")
        if written is None or not written.isdigit():
            raise ValueError(
                f"clickhouse QuerySummary missing written_rows: {result.summary!r}"
            )
        return int(written)
    raise ValueError(f"clickhouse command unexpected result type: {type(result).__name__}")


def _schema_from_rows(rows: Sequence[Sequence[JsonValue]]) -> DatasourceSchemaSnapshot:
    tables: dict[str, DatasourceTable] = {}
    order: list[str] = []
    for row in rows:
        if len(row) != 4:
            raise ValueError("clickhouse system.columns row must have 4 cells")
        database_name, table_name, column_name, data_type = row
        if not isinstance(table_name, str) or not isinstance(column_name, str):
            raise ValueError("clickhouse column identity must be text")
        if not isinstance(data_type, str):
            raise ValueError("clickhouse column type must be text")
        prefix = database_name if isinstance(database_name, str) and database_name else ""
        key = f"{prefix}.{table_name}" if prefix else table_name
        table = tables.get(key)
        if table is None:
            table = DatasourceTable(table_name=key, columns=[])
            tables[key] = table
            order.append(key)
        table.columns.append(DatasourceColumn(name=column_name, data_type=data_type))
    return DatasourceSchemaSnapshot(tables=[tables[key] for key in order])
