"""Typed ClickHouse async client surface used by the platform."""

from collections.abc import Mapping, Sequence

from clickhouse_connect.driver.summary import QuerySummary

class QueryResult:
    result_rows: Sequence[Sequence[object]]
    column_names: Sequence[str]

class AsyncClient:
    async def query(
        self,
        query: str,
        parameters: Mapping[str, object] | None = None,
    ) -> QueryResult: ...
    async def command(
        self,
        cmd: str,
        parameters: Mapping[str, object] | None = None,
    ) -> str | int | Sequence[str] | QuerySummary: ...
    async def close(self) -> None: ...
