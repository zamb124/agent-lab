"""Driver statement_timeout_ms reaches mysql/clickhouse connect kwargs (live TCP)."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

import pytest

from core.datasources.drivers.clickhouse import ClickHouseDatasourceDriver
from core.datasources.drivers.mysql import MysqlDatasourceDriver
from core.datasources.drivers.sql_endpoint import statement_timeout_connect_seconds
from core.datasources.models import (
    DatasourceConnection,
    DatasourceSqlOperation,
    DatasourceSslMode,
)

_TESTNET_HOST = "192.0.2.1"
_TIMEOUT_MS = 1_000


def test_statement_timeout_connect_seconds_ceils() -> None:
    assert statement_timeout_connect_seconds(1) == 1
    assert statement_timeout_connect_seconds(1000) == 1
    assert statement_timeout_connect_seconds(15000) == 15
    assert statement_timeout_connect_seconds(15001) == 16


def _timeout_connection(*, connector_id: str, port: int) -> DatasourceConnection:
    now = datetime.now(timezone.utc)
    return DatasourceConnection(
        datasource_id="ds_timeout",
        company_id="system",
        connector_id=connector_id,
        name="timeout probe",
        host=_TESTNET_HOST,
        port=port,
        database_name="probe",
        username="probe",
        ssl_mode=DatasourceSslMode.DISABLE,
        allowed_operations=[DatasourceSqlOperation.SELECT],
        statement_timeout_ms=_TIMEOUT_MS,
        owner_user_id="timeout-user",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_mysql_connect_honors_statement_timeout() -> None:
    driver = MysqlDatasourceDriver()
    started = perf_counter()
    with pytest.raises(Exception):
        _ = await driver.test(_timeout_connection(connector_id="mysql", port=3306), "probe")
    elapsed_s = perf_counter() - started
    assert elapsed_s < 8


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_clickhouse_connect_honors_statement_timeout() -> None:
    driver = ClickHouseDatasourceDriver()
    started = perf_counter()
    with pytest.raises(Exception):
        _ = await driver.test(
            _timeout_connection(connector_id="clickhouse", port=8123), "probe"
        )
    elapsed_s = perf_counter() - started
    assert elapsed_s < 8
