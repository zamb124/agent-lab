"""Каталог platform-коннекторов datasource (штамп драйвера, не NodeType)."""

from __future__ import annotations

from core.datasources.models import (
    DatasourceConnectorSpec,
    DatasourceExecutorKind,
    DatasourceOperation,
)
from core.types import JsonObject, require_json_object

_SQL_CREDENTIAL_SCHEMA: JsonObject = require_json_object(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "host": {"type": "string"},
            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "database_name": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "ssl_mode": {
                "type": "string",
                "enum": ["disable", "require", "verify-full"],
            },
        },
        "required": ["host", "port", "database_name", "username", "password"],
    },
    "sql_credential_schema",
)

_SQL_OPERATIONS = (
    DatasourceOperation.INTROSPECT,
    DatasourceOperation.QUERY,
    DatasourceOperation.EXECUTE,
)

POSTGRES_CONNECTOR = DatasourceConnectorSpec(
    connector_id="postgres",
    name="PostgreSQL",
    description="SQL query/schema к живой базе Postgres",
    executor=DatasourceExecutorKind.PLATFORM,
    icon="database",
    credential_schema=_SQL_CREDENTIAL_SCHEMA,
    operations=list(_SQL_OPERATIONS),
)

MYSQL_CONNECTOR = DatasourceConnectorSpec(
    connector_id="mysql",
    name="MySQL",
    description="SQL query/schema к живой базе MySQL",
    executor=DatasourceExecutorKind.PLATFORM,
    icon="database",
    credential_schema=_SQL_CREDENTIAL_SCHEMA,
    operations=list(_SQL_OPERATIONS),
)

CLICKHOUSE_CONNECTOR = DatasourceConnectorSpec(
    connector_id="clickhouse",
    name="ClickHouse",
    description="SQL query/schema к живой базе ClickHouse",
    executor=DatasourceExecutorKind.PLATFORM,
    icon="database",
    credential_schema=_SQL_CREDENTIAL_SCHEMA,
    operations=list(_SQL_OPERATIONS),
)

PLATFORM_CONNECTORS: tuple[DatasourceConnectorSpec, ...] = (
    POSTGRES_CONNECTOR,
    MYSQL_CONNECTOR,
    CLICKHOUSE_CONNECTOR,
)

PLATFORM_CONNECTOR_IDS: frozenset[str] = frozenset(
    spec.connector_id for spec in PLATFORM_CONNECTORS
)


def platform_connector(connector_id: str) -> DatasourceConnectorSpec:
    for spec in PLATFORM_CONNECTORS:
        if spec.connector_id == connector_id:
            return spec
    raise ValueError(f"unknown platform connector_id: {connector_id}")
