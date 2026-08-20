"""Исполнение SQL-протокола datasource одним драйвером."""

from __future__ import annotations

from typing import Protocol

from core.datasources.models import (
    DatasourceConnection,
    DatasourceExecuteResult,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceTestResult,
)
from core.types import JsonObject


class DatasourceDriver(Protocol):
    async def test(self, connection: DatasourceConnection, password: str) -> DatasourceTestResult: ...

    async def introspect(
        self, connection: DatasourceConnection, password: str
    ) -> DatasourceSchemaSnapshot: ...

    async def query(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceQueryResult: ...

    async def execute(
        self,
        connection: DatasourceConnection,
        password: str,
        *,
        sql: str,
        params: JsonObject,
    ) -> DatasourceExecuteResult: ...


