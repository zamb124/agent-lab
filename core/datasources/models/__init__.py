"""Datasource: одна таблица — один модуль."""

from core.datasources.models.connection import (
    DatasourceConnection,
)
from core.datasources.models.connector_spec import (
    DatasourceConnectorSpec,
)
from core.datasources.models.contracts import (
    DatasourceColumn,
    DatasourceConnectionCreate,
    DatasourceConnectionPatch,
    DatasourceConnectionPatchPayload,
    DatasourceConnectorUpsert,
    DatasourceExecuteResult,
    DatasourceExecutorKind,
    DatasourceListPayload,
    DatasourceOperation,
    DatasourceProtocolResult,
    DatasourceQueryResult,
    DatasourceSchemaArgs,
    DatasourceSchemaSnapshot,
    DatasourceSqlCallArgs,
    DatasourceSqlOperation,
    DatasourceSqlRequest,
    DatasourceSslMode,
    DatasourceTable,
    DatasourceTestResult,
)

__all__ = [
    "DatasourceColumn",
    "DatasourceConnection",
    "DatasourceConnectionCreate",
    "DatasourceConnectionPatch",
    "DatasourceConnectionPatchPayload",
    "DatasourceConnectorSpec",
    "DatasourceConnectorUpsert",
    "DatasourceExecuteResult",
    "DatasourceExecutorKind",
    "DatasourceListPayload",
    "DatasourceOperation",
    "DatasourceProtocolResult",
    "DatasourceQueryResult",
    "DatasourceSchemaArgs",
    "DatasourceSqlCallArgs",
    "DatasourceSqlRequest",
    "DatasourceSchemaSnapshot",
    "DatasourceSqlOperation",
    "DatasourceSslMode",
    "DatasourceTable",
    "DatasourceTestResult",
]
