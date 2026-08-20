"""Общие проверки SQL-endpoint для platform-драйверов."""

from __future__ import annotations

from core.datasources.deny_list import assert_datasource_host_allowed
from core.datasources.models import DatasourceConnection, DatasourceSslMode


def require_sql_endpoint(
    connection: DatasourceConnection,
) -> tuple[str, int, str, str, DatasourceSslMode]:
    host = connection.host
    port = connection.port
    database_name = connection.database_name
    username = connection.username
    if host is None or not host.strip():
        raise ValueError(f"datasource {connection.datasource_id}: host is required")
    if port is None:
        raise ValueError(f"datasource {connection.datasource_id}: port is required")
    if database_name is None or not database_name.strip():
        raise ValueError(f"datasource {connection.datasource_id}: database_name is required")
    if username is None or not username.strip():
        raise ValueError(f"datasource {connection.datasource_id}: username is required")
    assert_datasource_host_allowed(host, port, database_name)
    return host, port, database_name, username, connection.ssl_mode


def statement_timeout_connect_seconds(timeout_ms: int) -> int:
    seconds = (timeout_ms + 999) // 1000
    if seconds < 1:
        raise ValueError(f"statement_timeout_ms {timeout_ms} must yield at least 1s")
    return seconds
