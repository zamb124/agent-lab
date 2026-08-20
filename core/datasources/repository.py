"""SQL-репозиторий DatasourceConnection / company connector specs (shared БД)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

from sqlalchemy import select

from core.datasources.catalog import PLATFORM_CONNECTOR_IDS, platform_connector
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectorSpec,
    DatasourceExecutorKind,
    DatasourceOperation,
    DatasourceSqlOperation,
    DatasourceSslMode,
)
from core.db.database import get_session_factory
from core.db.models.platform import DatasourceConnectionRecord, DatasourceConnectorRecord
from core.types import require_json_array, require_json_object


def _sql_operations(raw_operations: object, *, label: str) -> list[DatasourceSqlOperation]:
    items = require_json_array(raw_operations, label)
    if not items:
        raise ValueError(f"{label}: allowed_operations must be a non-empty list")
    operations: list[DatasourceSqlOperation] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label}: allowed_operations items must be strings")
        operations.append(DatasourceSqlOperation(item))
    return operations


def _protocol_operations(raw_operations: object, *, label: str) -> list[DatasourceOperation]:
    items = require_json_array(raw_operations, label)
    if not items:
        raise ValueError(f"{label}: operations must be a non-empty list")
    operations: list[DatasourceOperation] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label}: operations items must be strings")
        operations.append(DatasourceOperation(item))
    return operations


def _connection_from_record(record: DatasourceConnectionRecord) -> DatasourceConnection:
    return DatasourceConnection(
        datasource_id=record.datasource_id,
        company_id=record.company_id,
        connector_id=record.connector_id,
        name=record.name,
        host=record.host,
        port=record.port,
        database_name=record.database_name,
        username=record.username,
        password_encrypted=record.password_encrypted,
        ssl_mode=DatasourceSslMode(record.ssl_mode),
        allowed_operations=_sql_operations(
            record.allowed_operations,
            label=f"datasource {record.datasource_id}",
        ),
        statement_timeout_ms=record.statement_timeout_ms,
        max_rows=record.max_rows,
        mcp_server_id=record.mcp_server_id,
        flow_id=record.flow_id,
        flow_branch_id=record.flow_branch_id,
        owner_user_id=record.owner_user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _connector_from_record(record: DatasourceConnectorRecord) -> DatasourceConnectorSpec:
    return DatasourceConnectorSpec(
        connector_id=record.connector_id,
        name=record.name,
        description=record.description,
        executor=DatasourceExecutorKind(record.executor),
        icon=record.icon,
        credential_schema=require_json_object(
            record.credential_schema, "datasource_connector.credential_schema"
        ),
        operations=_protocol_operations(
            record.operations,
            label=f"connector {record.connector_id}",
        ),
        mcp_server_id=record.mcp_server_id,
        mcp_introspect_tool=record.mcp_introspect_tool,
        mcp_query_tool=record.mcp_query_tool,
        mcp_execute_tool=record.mcp_execute_tool,
        flow_id=record.flow_id,
        flow_branch_id=record.flow_branch_id,
    )


class DatasourceConnectionRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def get(self, datasource_id: str) -> DatasourceConnection | None:
        if not datasource_id.strip():
            raise ValueError("datasource_id is required")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectionRecord).where(
                    DatasourceConnectionRecord.datasource_id == datasource_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _connection_from_record(row)

    async def list_by_company(self, company_id: str) -> list[DatasourceConnection]:
        if not company_id.strip():
            raise ValueError("company_id is required")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectionRecord)
                .where(DatasourceConnectionRecord.company_id == company_id)
                .order_by(DatasourceConnectionRecord.name, DatasourceConnectionRecord.datasource_id)
            )
            return [_connection_from_record(row) for row in result.scalars().all()]

    async def insert(self, connection: DatasourceConnection) -> DatasourceConnection:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            session.add(_record_from_connection(connection))
            await session.commit()
        stored = await self.get(connection.datasource_id)
        if stored is None:
            raise RuntimeError(
                f"datasource {connection.datasource_id} missing after insert"
            )
        return stored

    async def update(self, connection: DatasourceConnection) -> DatasourceConnection:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectionRecord).where(
                    DatasourceConnectionRecord.datasource_id == connection.datasource_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"datasource not found: {connection.datasource_id}")
            _apply_connection(row, connection)
            await session.commit()
        stored = await self.get(connection.datasource_id)
        if stored is None:
            raise RuntimeError(
                f"datasource {connection.datasource_id} missing after update"
            )
        return stored

    async def delete(self, datasource_id: str) -> None:
        if not datasource_id.strip():
            raise ValueError("datasource_id is required")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectionRecord).where(
                    DatasourceConnectionRecord.datasource_id == datasource_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"datasource not found: {datasource_id}")
            await session.delete(row)
            await session.commit()


class DatasourceConnectorRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: Final[str] = db_url

    async def get(
        self, company_id: str, connector_id: str
    ) -> DatasourceConnectorSpec | None:
        if connector_id in PLATFORM_CONNECTOR_IDS:
            return platform_connector(connector_id)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectorRecord).where(
                    DatasourceConnectorRecord.company_id == company_id,
                    DatasourceConnectorRecord.connector_id == connector_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _connector_from_record(row)

    async def list_for_company(self, company_id: str) -> list[DatasourceConnectorSpec]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectorRecord)
                .where(DatasourceConnectorRecord.company_id == company_id)
                .order_by(DatasourceConnectorRecord.name, DatasourceConnectorRecord.connector_id)
            )
            stamped = [_connector_from_record(row) for row in result.scalars().all()]
        platform = list(PLATFORM_CONNECTOR_IDS)
        platform_specs = [platform_connector(item) for item in sorted(platform)]
        return platform_specs + stamped

    async def upsert(
        self,
        company_id: str,
        spec: DatasourceConnectorSpec,
        *,
        owner_user_id: str,
    ) -> DatasourceConnectorSpec:
        if spec.connector_id in PLATFORM_CONNECTOR_IDS:
            raise ValueError(
                f"connector_id {spec.connector_id!r} is reserved for platform drivers"
            )
        now = datetime.now(timezone.utc)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(DatasourceConnectorRecord).where(
                    DatasourceConnectorRecord.company_id == company_id,
                    DatasourceConnectorRecord.connector_id == spec.connector_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(
                    DatasourceConnectorRecord(
                        company_id=company_id,
                        connector_id=spec.connector_id,
                        name=spec.name,
                        description=spec.description,
                        executor=str(spec.executor),
                        icon=spec.icon,
                        credential_schema=spec.credential_schema,
                        operations=[str(item) for item in spec.operations],
                        mcp_server_id=spec.mcp_server_id,
                        mcp_introspect_tool=spec.mcp_introspect_tool,
                        mcp_query_tool=spec.mcp_query_tool,
                        mcp_execute_tool=spec.mcp_execute_tool,
                        flow_id=spec.flow_id,
                        flow_branch_id=spec.flow_branch_id,
                        owner_user_id=owner_user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.name = spec.name
                row.description = spec.description
                row.executor = str(spec.executor)
                row.icon = spec.icon
                row.credential_schema = spec.credential_schema
                row.operations = [str(item) for item in spec.operations]
                row.mcp_server_id = spec.mcp_server_id
                row.mcp_introspect_tool = spec.mcp_introspect_tool
                row.mcp_query_tool = spec.mcp_query_tool
                row.mcp_execute_tool = spec.mcp_execute_tool
                row.flow_id = spec.flow_id
                row.flow_branch_id = spec.flow_branch_id
                row.updated_at = now
            await session.commit()
        stored = await self.get(company_id, spec.connector_id)
        if stored is None:
            raise RuntimeError(f"connector {spec.connector_id} missing after upsert")
        return stored


def _record_from_connection(connection: DatasourceConnection) -> DatasourceConnectionRecord:
    return DatasourceConnectionRecord(
        datasource_id=connection.datasource_id,
        company_id=connection.company_id,
        connector_id=connection.connector_id,
        name=connection.name,
        host=connection.host,
        port=connection.port,
        database_name=connection.database_name,
        username=connection.username,
        password_encrypted=connection.password_encrypted,
        ssl_mode=str(connection.ssl_mode),
        allowed_operations=[str(item) for item in connection.allowed_operations],
        statement_timeout_ms=connection.statement_timeout_ms,
        max_rows=connection.max_rows,
        mcp_server_id=connection.mcp_server_id,
        flow_id=connection.flow_id,
        flow_branch_id=connection.flow_branch_id,
        owner_user_id=connection.owner_user_id,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _apply_connection(
    row: DatasourceConnectionRecord, connection: DatasourceConnection
) -> None:
    row.connector_id = connection.connector_id
    row.name = connection.name
    row.host = connection.host
    row.port = connection.port
    row.database_name = connection.database_name
    row.username = connection.username
    row.password_encrypted = connection.password_encrypted
    row.ssl_mode = str(connection.ssl_mode)
    row.allowed_operations = [str(item) for item in connection.allowed_operations]
    row.statement_timeout_ms = connection.statement_timeout_ms
    row.max_rows = connection.max_rows
    row.mcp_server_id = connection.mcp_server_id
    row.flow_id = connection.flow_id
    row.flow_branch_id = connection.flow_branch_id
    row.updated_at = connection.updated_at
