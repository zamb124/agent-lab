"""Platform MySQL driver для DatasourceProtocol."""

from __future__ import annotations

from ssl import CERT_NONE, CERT_REQUIRED, SSLContext, create_default_context
from time import perf_counter

from asyncmy import connect
from asyncmy.connection import Connection as MysqlConnection

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
from core.datasources.sql_policy import bind_named_params, rewrite_placeholders_percent
from core.types import JsonObject, JsonValue


def _columns_sql_by_table_and_position_asc() -> str:
    """Колонки текущей базы, ORDER BY TABLE_NAME ASC, ORDINAL_POSITION ASC."""
    return (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )


class MysqlDatasourceDriver:
    async def test(self, connection: DatasourceConnection, password: str) -> DatasourceTestResult:
        started = perf_counter()
        conn = await self._connect(connection, password)
        try:
            async with conn.cursor() as cursor:
                _ = await cursor.execute("SELECT VERSION()")
                row = await cursor.fetchone()
        finally:
            conn.close()
        if row is None or row[0] is None:
            raise ValueError("mysql test: VERSION() did not return text")
        version = str(row[0])
        latency_ms = int((perf_counter() - started) * 1000)
        return DatasourceTestResult(ok=True, latency_ms=latency_ms, server_version=version)

    async def introspect(
        self, connection: DatasourceConnection, password: str
    ) -> DatasourceSchemaSnapshot:
        conn = await self._connect(connection, password)
        try:
            async with conn.cursor() as cursor:
                _ = await cursor.execute(_columns_sql_by_table_and_position_asc())
                rows = await cursor.fetchall()
        finally:
            conn.close()
        return _schema_from_rows(rows)

    async def query(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceQueryResult:
        rewritten, values = bind_named_params(sql, params)
        mysql_sql = rewrite_placeholders_percent(rewritten)
        conn = await self._connect(connection, password)
        try:
            async with conn.cursor() as cursor:
                _ = await cursor.execute(mysql_sql, _mysql_args(values))
                records = await cursor.fetchall()
                description = cursor.description
        finally:
            conn.close()
        columns = _columns_from_description(description)
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
        rewritten, values = bind_named_params(sql, params)
        mysql_sql = rewrite_placeholders_percent(rewritten)
        conn = await self._connect(connection, password)
        try:
            async with conn.cursor() as cursor:
                _ = await cursor.execute(mysql_sql, _mysql_args(values))
                rowcount = cursor.rowcount
            await conn.commit()
        finally:
            conn.close()
        if rowcount < 0:
            raise ValueError(f"mysql execute rowcount invalid: {rowcount}")
        return DatasourceExecuteResult(rowcount=int(rowcount))

    async def _connect(self, connection: DatasourceConnection, password: str) -> MysqlConnection:
        host, port, database_name, username, ssl_mode = require_sql_endpoint(connection)
        timeout_s = statement_timeout_connect_seconds(connection.statement_timeout_ms)
        conn = await connect(
            host=host,
            port=port,
            user=username,
            password=password,
            db=database_name,
            ssl=_mysql_ssl(ssl_mode),
            connect_timeout=timeout_s,
        )
        try:
            async with conn.cursor() as cursor:
                _ = await cursor.execute(
                    "SET SESSION max_execution_time = %s",
                    (connection.statement_timeout_ms,),
                )
        except Exception:
            conn.close()
            raise
        return conn


def _mysql_ssl(ssl_mode: DatasourceSslMode) -> SSLContext | None:
    match ssl_mode:
        case DatasourceSslMode.DISABLE:
            return None
        case DatasourceSslMode.REQUIRE:
            context = create_default_context()
            context.check_hostname = False
            context.verify_mode = CERT_NONE
            return context
        case DatasourceSslMode.VERIFY_FULL:
            context = create_default_context()
            context.check_hostname = True
            context.verify_mode = CERT_REQUIRED
            return context


def _mysql_args(values: list[JsonValue]) -> tuple[object, ...]:
    return tuple(values)


def _columns_from_description(
    description: tuple[tuple[object, ...], ...] | None,
) -> list[str]:
    if description is None:
        return []
    columns: list[str] = []
    for item in description:
        name = item[0]
        if not isinstance(name, str) or not name:
            raise ValueError("mysql cursor.description column name required")
        columns.append(name)
    return columns


def _schema_from_rows(rows: list[tuple[object, ...]]) -> DatasourceSchemaSnapshot:
    tables: dict[str, DatasourceTable] = {}
    order: list[str] = []
    for row in rows:
        if len(row) != 4:
            raise ValueError("mysql information_schema row must have 4 cells")
        schema_name, table_name, column_name, data_type = row
        if not isinstance(table_name, str) or not isinstance(column_name, str):
            raise ValueError("mysql information_schema identity must be text")
        if not isinstance(data_type, str):
            raise ValueError("mysql information_schema data_type must be text")
        prefix = schema_name if isinstance(schema_name, str) and schema_name else ""
        key = f"{prefix}.{table_name}" if prefix else table_name
        table = tables.get(key)
        if table is None:
            table = DatasourceTable(table_name=key, columns=[])
            tables[key] = table
            order.append(key)
        table.columns.append(DatasourceColumn(name=column_name, data_type=data_type))
    return DatasourceSchemaSnapshot(tables=[tables[key] for key in order])
