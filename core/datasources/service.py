"""DatasourceService: Authz + protocol dispatch (platform / mcp / flow)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from core.authz.errors import AuthzDenied
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.context import require_context
from core.datasources.authz.tuples import (
    datasource_company_link,
    datasource_company_viewer_tuple,
    datasource_owner_tuple,
    datasource_platform_link,
)
from core.datasources.catalog import PLATFORM_CONNECTOR_IDS, platform_connector
from core.datasources.drivers import platform_driver
from core.datasources.drivers.sql_endpoint import require_sql_endpoint
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectionCreate,
    DatasourceConnectionPatch,
    DatasourceConnectorSpec,
    DatasourceConnectorUpsert,
    DatasourceExecuteResult,
    DatasourceExecutorKind,
    DatasourceOperation,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceTestResult,
)
from core.datasources.sql_policy import assert_operation_allowed
from core.secrets.crypto import decrypt_secret, encrypt_secret
from core.types import JsonObject


class DatasourceRemoteExecutor(Protocol):
    async def run(
        self,
        *,
        spec: DatasourceConnectorSpec,
        connection: DatasourceConnection,
        operation: DatasourceOperation,
        sql: str | None,
        params: JsonObject,
        password: str | None,
        as_test: bool,
    ) -> (
        DatasourceSchemaSnapshot
        | DatasourceQueryResult
        | DatasourceExecuteResult
        | DatasourceTestResult
    ): ...


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasourceExecutors:
    """Исполнители коннекторов вне платформы; их собирает владелец runtime, который вызывает datasource."""

    mcp: DatasourceRemoteExecutor
    flow: DatasourceRemoteExecutor

    def for_kind(self, kind: DatasourceExecutorKind) -> DatasourceRemoteExecutor:
        if kind == DatasourceExecutorKind.MCP:
            return self.mcp
        if kind == DatasourceExecutorKind.FLOW:
            return self.flow
        raise ValueError(f"no remote executor for {kind}")


class DatasourceService:
    def __init__(self, *, authz: AuthzService) -> None:
        self._authz: AuthzService = authz


    async def _get_connector(self, company_id: str, connector_id: str) -> DatasourceConnectorSpec | None:
        if connector_id in PLATFORM_CONNECTOR_IDS:
            return platform_connector(connector_id)
        return await DatasourceConnectorSpec.by_connector_id(company_id, connector_id)

    async def _list_connectors_for_company(self, company_id: str) -> list[DatasourceConnectorSpec]:
        stamped = await DatasourceConnectorSpec.list_stamped_for_company(company_id)
        platform_specs = [platform_connector(item) for item in sorted(PLATFORM_CONNECTOR_IDS)]
        return platform_specs + stamped


    async def list_connectors(self) -> list[DatasourceConnectorSpec]:
        company_id = _company_id()
        await self._authz.require_can_view(AuthzObject.company(company_id))
        return await self._list_connectors_for_company(company_id)

    async def upsert_connector(
        self, payload: DatasourceConnectorUpsert
    ) -> DatasourceConnectorSpec:
        company_id = _company_id()
        await self._authz.require_can_view(AuthzObject.company(company_id))
        if payload.executor == DatasourceExecutorKind.PLATFORM:
            raise ValueError("company stamp cannot use executor=platform")
        spec = DatasourceConnectorSpec.model_validate(payload.model_dump(mode="python"))
        if spec.connector_id in PLATFORM_CONNECTOR_IDS:
            raise ValueError(f"connector_id {spec.connector_id!r} is reserved for platform drivers")
        return await DatasourceConnectorSpec.upsert_by_connector_id(
            company_id, spec, owner_user_id=_user_id()
        )

    async def list_connections(self) -> list[DatasourceConnection]:
        company_id = _company_id()
        user_id = _user_id()
        await self._authz.require_can_view(AuthzObject.company(company_id))
        candidates = await DatasourceConnection.list_by_company(company_id)
        if not candidates:
            return []
        allowed = await self._authz.batch_check(
            [
                AuthzCheckItem(
                    subject=AuthzSubject.user(user_id),
                    relation=AuthzRelation.CAN_VIEW,
                    obj=AuthzObject.datasource(
                        item.datasource_id, company_id=company_id
                    ),
                    correlation_id=item.datasource_id,
                )
                for item in candidates
            ]
        )
        return [
            item
            for item, visible in zip(candidates, allowed, strict=True)
            if visible
        ]

    async def get_connection(self, datasource_id: str) -> DatasourceConnection:
        connection = await self._require_connection(datasource_id)
        await self._authz.require_can_view(
            AuthzObject.datasource(
                connection.datasource_id, company_id=connection.company_id
            )
        )
        return connection

    async def create_connection(
        self, payload: DatasourceConnectionCreate
    ) -> DatasourceConnection:
        company_id = _company_id()
        user_id = _user_id()
        await self._authz.require_can_view(AuthzObject.company(company_id))
        spec = await self._require_spec(company_id, payload.connector_id)
        now = datetime.now(timezone.utc)
        datasource_id = f"ds_{uuid4().hex}"
        password_encrypted = _encrypt_optional(payload.password, spec)
        connection = DatasourceConnection(
            datasource_id=datasource_id,
            company_id=company_id,
            connector_id=spec.connector_id,
            name=payload.name,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            password_encrypted=password_encrypted,
            ssl_mode=payload.ssl_mode,
            allowed_operations=payload.allowed_operations,
            statement_timeout_ms=payload.statement_timeout_ms,
            max_rows=payload.max_rows,
            mcp_server_id=payload.mcp_server_id,
            flow_id=payload.flow_id,
            flow_branch_id=payload.flow_branch_id,
            owner_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        _assert_create_shape(spec, connection, payload.password)
        stored = await DatasourceConnection.insert(connection)
        try:
            await self._authz.write(
                [
                    datasource_company_link(datasource_id, company_id),
                    datasource_platform_link(datasource_id, company_id=company_id),
                    datasource_owner_tuple(
                        datasource_id, user_id, company_id=company_id
                    ),
                    datasource_company_viewer_tuple(datasource_id, company_id),
                ]
            )
        except Exception:
            deleted = await DatasourceConnection.delete_by_id(datasource_id)
            if not deleted:
                raise ValueError(f"datasource not found: {datasource_id}")
            raise
        return stored

    async def patch_connection(
        self, datasource_id: str, payload: DatasourceConnectionPatch
    ) -> DatasourceConnection:
        current = await self._require_connection(datasource_id)
        await self._authz.require_can_edit(
            AuthzObject.datasource(
                current.datasource_id, company_id=current.company_id
            )
        )
        spec = await self._require_spec(current.company_id, current.connector_id)
        password_encrypted = current.password_encrypted
        if payload.password is not None:
            password_encrypted = encrypt_secret(payload.password)
        patched = current.model_copy(
            update={
                "name": payload.name if payload.name is not None else current.name,
                "host": payload.host if payload.host is not None else current.host,
                "port": payload.port if payload.port is not None else current.port,
                "database_name": (
                    payload.database_name
                    if payload.database_name is not None
                    else current.database_name
                ),
                "username": (
                    payload.username if payload.username is not None else current.username
                ),
                "password_encrypted": password_encrypted,
                "ssl_mode": payload.ssl_mode if payload.ssl_mode is not None else current.ssl_mode,
                "allowed_operations": (
                    payload.allowed_operations
                    if payload.allowed_operations is not None
                    else current.allowed_operations
                ),
                "statement_timeout_ms": (
                    payload.statement_timeout_ms
                    if payload.statement_timeout_ms is not None
                    else current.statement_timeout_ms
                ),
                "max_rows": payload.max_rows if payload.max_rows is not None else current.max_rows,
                "mcp_server_id": (
                    payload.mcp_server_id
                    if payload.mcp_server_id is not None
                    else current.mcp_server_id
                ),
                "flow_id": payload.flow_id if payload.flow_id is not None else current.flow_id,
                "flow_branch_id": (
                    payload.flow_branch_id
                    if payload.flow_branch_id is not None
                    else current.flow_branch_id
                ),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _assert_stored_shape(spec, patched)
        return await DatasourceConnection.update_connection(patched)

    async def delete_connection(self, datasource_id: str) -> None:
        current = await self._require_connection(datasource_id)
        obj = AuthzObject.datasource(
            current.datasource_id, company_id=current.company_id
        )
        await self._authz.require_can_edit(obj)
        deletes = await self._authz.list_tuples(obj)
        if deletes:
            await self._authz.delete(deletes)
        try:
            deleted = await DatasourceConnection.delete_by_id(datasource_id)
            if not deleted:
                raise ValueError(f"datasource not found: {datasource_id}")
        except Exception:
            if deletes:
                await self._authz.write(deletes)
            raise

    async def test(
        self, datasource_id: str, *, executors: DatasourceExecutors
    ) -> DatasourceTestResult:
        result = await self._dispatch(
            datasource_id,
            DatasourceOperation.INTROSPECT,
            sql=None,
            params={},
            as_test=True,
            executors=executors,
        )
        if not isinstance(result, DatasourceTestResult):
            raise ValueError("datasource test must return DatasourceTestResult")
        return result

    async def introspect(
        self, datasource_id: str, *, executors: DatasourceExecutors
    ) -> DatasourceSchemaSnapshot:
        result = await self._dispatch(
            datasource_id,
            DatasourceOperation.INTROSPECT,
            sql=None,
            params={},
            as_test=False,
            executors=executors,
        )
        if not isinstance(result, DatasourceSchemaSnapshot):
            raise ValueError("introspect must return DatasourceSchemaSnapshot")
        return result

    async def query(
        self,
        datasource_id: str,
        sql: str,
        params: JsonObject,
        *,
        executors: DatasourceExecutors,
    ) -> DatasourceQueryResult:
        result = await self._dispatch(
            datasource_id,
            DatasourceOperation.QUERY,
            sql=sql,
            params=params,
            as_test=False,
            executors=executors,
        )
        if not isinstance(result, DatasourceQueryResult):
            raise ValueError("query must return DatasourceQueryResult")
        return result

    async def execute(
        self,
        datasource_id: str,
        sql: str,
        params: JsonObject,
        *,
        executors: DatasourceExecutors,
    ) -> DatasourceExecuteResult:
        result = await self._dispatch(
            datasource_id,
            DatasourceOperation.EXECUTE,
            sql=sql,
            params=params,
            as_test=False,
            executors=executors,
        )
        if not isinstance(result, DatasourceExecuteResult):
            raise ValueError("execute must return DatasourceExecuteResult")
        return result

    async def _dispatch(
        self,
        datasource_id: str,
        operation: DatasourceOperation,
        *,
        sql: str | None,
        params: JsonObject,
        as_test: bool,
        executors: DatasourceExecutors,
    ) -> (
        DatasourceSchemaSnapshot
        | DatasourceQueryResult
        | DatasourceExecuteResult
        | DatasourceTestResult
    ):
        connection = await self._require_connection(datasource_id)
        obj = AuthzObject.datasource(
            connection.datasource_id, company_id=connection.company_id
        )
        if operation is DatasourceOperation.EXECUTE:
            await self._authz.require_can_edit(obj)
        else:
            await self._authz.require_can_view(obj)
        spec = await self._require_spec(connection.company_id, connection.connector_id)
        if operation not in spec.operations and not as_test:
            raise ValueError(
                f"connector {spec.connector_id} does not support {operation.value}"
            )
        if sql is not None:
            _ = assert_operation_allowed(
                sql,
                protocol=operation,
                allowed=connection.allowed_operations,
            )
        if spec.executor == DatasourceExecutorKind.PLATFORM:
            password = _require_password(connection)
            driver = platform_driver(spec.connector_id)
            if as_test:
                return await driver.test(connection, password)
            if sql is None and operation is not DatasourceOperation.INTROSPECT:
                raise ValueError(f"{operation.value} requires sql")
            match operation:
                case DatasourceOperation.INTROSPECT:
                    return await driver.introspect(connection, password)
                case DatasourceOperation.QUERY:
                    if sql is None:
                        raise ValueError("query requires sql")
                    return await driver.query(
                        connection, password, sql=sql, params=params
                    )
                case DatasourceOperation.EXECUTE:
                    if sql is None:
                        raise ValueError("execute requires sql")
                    return await driver.execute(
                        connection, password, sql=sql, params=params
                    )
        executor = executors.for_kind(spec.executor)
        run_operation = DatasourceOperation.INTROSPECT if as_test else operation
        return await executor.run(
            spec=spec,
            connection=connection,
            operation=run_operation,
            sql=sql,
            params=params,
            password=_optional_password(connection),
            as_test=as_test,
        )

    async def _require_connection(self, datasource_id: str) -> DatasourceConnection:
        connection = await DatasourceConnection.get(datasource_id)
        if connection is None:
            raise AuthzDenied(f"datasource not visible: {datasource_id}")
        if connection.company_id != _company_id():
            raise AuthzDenied(f"datasource not visible: {datasource_id}")
        return connection

    async def _require_spec(
        self, company_id: str, connector_id: str
    ) -> DatasourceConnectorSpec:
        spec = await self._get_connector(company_id, connector_id)
        if spec is None:
            raise ValueError(f"unknown connector_id: {connector_id}")
        return spec


def _company_id() -> str:
    company = require_context().active_company
    if company is None:
        raise ValueError("active_company is required")
    return company.company_id


def _user_id() -> str:
    return require_context().user.user_id


def _encrypt_optional(
    password: str | None, spec: DatasourceConnectorSpec
) -> str | None:
    if spec.executor == DatasourceExecutorKind.PLATFORM:
        if password is None or not password.strip():
            raise ValueError("platform datasource requires password")
        return encrypt_secret(password)
    if password is not None and password.strip():
        return encrypt_secret(password)
    return None


def _require_password(connection: DatasourceConnection) -> str:
    token = connection.password_encrypted
    if token is None or not token.strip():
        raise ValueError(
            f"datasource {connection.datasource_id}: password_encrypted is required"
        )
    return decrypt_secret(token)


def _optional_password(connection: DatasourceConnection) -> str | None:
    token = connection.password_encrypted
    if token is None or not token.strip():
        return None
    return decrypt_secret(token)


def _assert_create_shape(
    spec: DatasourceConnectorSpec,
    connection: DatasourceConnection,
    password: str | None,
) -> None:
    _assert_stored_shape(spec, connection)
    if spec.executor == DatasourceExecutorKind.PLATFORM:
        if password is None or not password.strip():
            raise ValueError("platform datasource requires password")


def _assert_stored_shape(
    spec: DatasourceConnectorSpec, connection: DatasourceConnection
) -> None:
    if spec.executor == DatasourceExecutorKind.PLATFORM:
        if connection.connector_id not in PLATFORM_CONNECTOR_IDS:
            raise ValueError(
                f"platform spec {spec.connector_id} cannot bind connector {connection.connector_id}"
            )
        _host, _port, _database_name, _username, _ssl_mode = require_sql_endpoint(connection)
        return
    if spec.executor == DatasourceExecutorKind.MCP:
        server_id = connection.mcp_server_id or spec.mcp_server_id
        if server_id is None or not server_id.strip():
            raise ValueError("mcp datasource requires mcp_server_id")
        return
    if spec.executor == DatasourceExecutorKind.FLOW:
        flow_id = connection.flow_id or spec.flow_id
        if flow_id is None or not flow_id.strip():
            raise ValueError("flow datasource requires flow_id")
        return
    raise ValueError(f"unsupported executor: {spec.executor}")
